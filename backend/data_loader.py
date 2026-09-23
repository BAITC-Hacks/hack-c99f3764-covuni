"""
Data Loader & In-Memory Cache Module
Halyk Bank — Career Quest (HackAlem AI)
Team 202453

Responsible for loading, validating, and caching the 4 foundational datasets:
- employees.json
- events.json
- skills.json
- activity_history.csv

Provides thread-safe dynamic ingestion of jury verification profiles without server restarts.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("career_quest.data_loader")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


# ==============================================================================
# Pydantic Data Models & Validation Schemas
# ==============================================================================

class SkillDefinition(BaseModel):
    id: Optional[str] = None
    name: str
    category: Optional[str] = "General"


class EventItem(BaseModel):
    id: str
    title: str
    format: str = "workshop"
    difficulty: Optional[str] = "intermediate"
    target_skills: List[str] = Field(default_factory=list)
    skill_gain: int = Field(default=1, ge=0)
    max_level: int = Field(default=5, ge=0, le=5)
    duration_hours: float = 0.0
    date: Optional[str] = None
    description: Optional[str] = ""


class EmployeeProfile(BaseModel):
    id: str
    name: str
    department: Optional[str] = ""
    current_role: str
    current_grade: str
    target_grade: str
    skills: Dict[str, int] = Field(default_factory=dict)
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict)
    is_custom: bool = False  # True if uploaded via jury verification endpoint


class CustomProfileUploadRequest(BaseModel):
    profiles: List[Dict[str, Any]] = Field(
        ...,
        description="List of custom candidate profiles to evaluate, bypasses standard single-factor assumptions."
    )


class CustomProfileUploadResponse(BaseModel):
    status: str
    loaded_count: int
    profile_ids: List[str]
    validation_errors: List[str] = Field(default_factory=list)


# ==============================================================================
# In-Memory Thread-Safe Data Layer
# ==============================================================================

class DataLoader:
    """
    Centralized In-Memory Data Store for HackAlem AI Career Quest.
    Guarantees thread-safe access and zero-downtime custom profile ingestion.
    """

    def __init__(self, data_dir: Optional[Union[str, Path]] = None) -> None:
        self.lock = RLock()
        self.data_dir = self._resolve_data_dir(data_dir)
        
        # Primary in-memory registries
        self._employees: Dict[str, EmployeeProfile] = {}
        self._custom_profiles: Dict[str, EmployeeProfile] = {}
        self._events: Dict[str, EventItem] = {}
        self._skills_catalog: Dict[str, SkillDefinition] = {}
        self._grade_requirements: Dict[str, Dict[str, Dict[str, int]]] = {}
        self._activity_history: pd.DataFrame = pd.DataFrame()

        self._initialized = False

    def _resolve_data_dir(self, data_dir: Optional[Union[str, Path]]) -> Path:
        """Resolve directory path with fallback priority: arg (if exists) -> env var (if exists) -> standard paths."""
        if data_dir:
            p = Path(data_dir)
            if p.is_dir():
                return p
        
        env_dir = os.getenv("DATA_DIR")
        if env_dir:
            p = Path(env_dir)
            if p.is_dir():
                return p
            
        # Try standard directory candidates
        candidates = [
            Path.cwd() / "data",
            Path(__file__).resolve().parent.parent / "data",
            Path(__file__).resolve().parent / "data",
            Path("/app/data"),
        ]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate

        return Path.cwd() / "data"

    def load_all(self) -> None:
        """Loads and parses all 4 dataset files into memory."""
        with self.lock:
            logger.info("Initializing dataset from directory: %s", self.data_dir)
            self._load_skills()
            self._load_events()
            self._load_employees()
            self._load_activity_history()
            self._initialized = True
            logger.info(
                "Data loading complete: %d employees, %d events, %d skills, %d history rows.",
                len(self._employees),
                len(self._events),
                len(self._skills_catalog),
                len(self._activity_history)
            )

    def _load_skills(self) -> None:
        skills_path = self.data_dir / "skills.json"
        if not skills_path.exists():
            logger.warning("skills.json not found at %s. Using empty registry.", skills_path)
            return

        try:
            with open(skills_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_skills = data.get("skills", [])
            for item in raw_skills:
                skill_obj = SkillDefinition(**item)
                self._skills_catalog[skill_obj.name] = skill_obj

            self._grade_requirements = data.get("grade_requirements", {})
            logger.info("Loaded %d skills and %d roles from skills.json", len(self._skills_catalog), len(self._grade_requirements))
        except Exception as e:
            logger.error("Failed to parse skills.json: %s", e)

    def _load_events(self) -> None:
        events_path = self.data_dir / "events.json"
        if not events_path.exists():
            logger.warning("events.json not found at %s. Using empty registry.", events_path)
            return

        try:
            with open(events_path, "r", encoding="utf-8") as f:
                raw_events = json.load(f)

            if isinstance(raw_events, list):
                for item in raw_events:
                    event = EventItem(**item)
                    self._events[event.id] = event
            logger.info("Loaded %d events from events.json", len(self._events))
        except Exception as e:
            logger.error("Failed to parse events.json: %s", e)

    def _load_employees(self) -> None:
        emp_path = self.data_dir / "employees.json"
        if not emp_path.exists():
            logger.warning("employees.json not found at %s. Using empty registry.", emp_path)
            return

        try:
            with open(emp_path, "r", encoding="utf-8") as f:
                raw_emps = json.load(f)

            if isinstance(raw_emps, list):
                for item in raw_emps:
                    emp = EmployeeProfile(**item, is_custom=False)
                    self._employees[emp.id] = emp
            logger.info("Loaded %d baseline employees from employees.json", len(self._employees))
        except Exception as e:
            logger.error("Failed to parse employees.json: %s", e)

    def _load_activity_history(self) -> None:
        hist_path = self.data_dir / "activity_history.csv"
        if not hist_path.exists():
            logger.warning("activity_history.csv not found at %s. Using empty DataFrame.", hist_path)
            self._activity_history = pd.DataFrame(
                columns=["employee_id", "event_id", "event_date", "status", "score", "feedback"]
            )
            return

        try:
            df = pd.read_csv(hist_path)
            # Standardize column types
            if "employee_id" in df.columns:
                df["employee_id"] = df["employee_id"].astype(str)
            if "event_id" in df.columns:
                df["event_id"] = df["event_id"].astype(str)
            self._activity_history = df
            logger.info("Loaded %d records from activity_history.csv", len(self._activity_history))
        except Exception as e:
            logger.error("Failed to parse activity_history.csv: %s", e)
            self._activity_history = pd.DataFrame()

    # ==========================================================================
    # Dynamic Custom Profiles Ingestion (Jury Killer Feature)
    # ==========================================================================

    def load_custom_profiles(
        self, profiles_data: List[Dict[str, Any]]
    ) -> Tuple[List[EmployeeProfile], List[str]]:
        """
        Dynamically validates and loads jury verification profiles into in-memory cache.
        Does not require server restart. Profiles immediately become queryable.
        
        Returns:
            Tuple[List[EmployeeProfile], List[str]]: Successfully loaded profiles, list of errors.
        """
        loaded: List[EmployeeProfile] = []
        errors: List[str] = []

        with self.lock:
            for idx, raw_profile in enumerate(profiles_data):
                try:
                    # Inject custom flag
                    profile_dict = dict(raw_profile)
                    profile_dict["is_custom"] = True

                    # Generate ID if missing
                    if "id" not in profile_dict or not profile_dict["id"]:
                        profile_dict["id"] = f"jury_custom_{len(self._custom_profiles) + 1}_{idx}"

                    profile = EmployeeProfile(**profile_dict)
                    
                    # Store in both master and custom lookup
                    self._employees[profile.id] = profile
                    self._custom_profiles[profile.id] = profile
                    loaded.append(profile)
                    logger.info("Dynamically ingested verification profile: %s (%s)", profile.id, profile.name)

                except ValidationError as ve:
                    err_msg = f"Profile #{idx} validation error: {ve.errors()}"
                    errors.append(err_msg)
                    logger.warning(err_msg)
                except Exception as ex:
                    err_msg = f"Profile #{idx} unexpected error: {str(ex)}"
                    errors.append(err_msg)
                    logger.error(err_msg)

        return loaded, errors

    # ==========================================================================
    # Accessors & Query Helpers for ML / Backend Team
    # ==========================================================================

    def get_employee(self, employee_id: str) -> Optional[EmployeeProfile]:
        """Fetch employee profile by ID (from base or custom)."""
        with self.lock:
            return self._employees.get(str(employee_id))

    def get_all_employees(self, include_custom: bool = True) -> List[EmployeeProfile]:
        """Fetch all employees registered in memory."""
        with self.lock:
            if include_custom:
                return list(self._employees.values())
            return [emp for emp in self._employees.values() if not emp.is_custom]

    def get_custom_profiles(self) -> List[EmployeeProfile]:
        """Fetch only dynamically uploaded jury verification profiles."""
        with self.lock:
            return list(self._custom_profiles.values())

    def get_events(self) -> List[EventItem]:
        """Fetch all events."""
        with self.lock:
            return list(self._events.values())

    def get_event(self, event_id: str) -> Optional[EventItem]:
        """Fetch a specific event by ID."""
        with self.lock:
            return self._events.get(str(event_id))

    def get_grade_requirements(self, role: str, target_grade: str) -> Dict[str, int]:
        """
        Returns required skills and minimum levels for a given role and grade.
        e.g., role='Backend Developer', target_grade='Senior' -> {'Python': 4, 'Kubernetes': 3, ...}
        """
        with self.lock:
            role_dict = self._grade_requirements.get(role, {})
            return role_dict.get(target_grade, {})

    def get_employee_history(self, employee_id: str) -> pd.DataFrame:
        """Returns 24-month historical participation logs for an employee."""
        with self.lock:
            if self._activity_history.empty or "employee_id" not in self._activity_history.columns:
                return pd.DataFrame()
            return self._activity_history[self._activity_history["employee_id"] == str(employee_id)].copy()

    def update_employee_skill(
        self, employee_id: str, skill_name: str, new_level: int
    ) -> Optional[EmployeeProfile]:
        """Updates a specific skill level for an employee in memory."""
        with self.lock:
            emp = self._employees.get(str(employee_id))
            if not emp:
                return None
            emp.skills[skill_name] = new_level
            if str(employee_id) in self._custom_profiles:
                self._custom_profiles[str(employee_id)].skills[skill_name] = new_level
            return emp

    def record_activity(
        self,
        employee_id: str,
        event_id: str,
        status: str = "completed",
        score: float = 5.0,
        feedback: str = "Завершено через Career Quest",
        event_date: Optional[str] = None,
    ) -> None:
        """Appends a new participation record to activity history."""
        from datetime import date
        with self.lock:
            new_row = {
                "employee_id": str(employee_id),
                "event_id": str(event_id),
                "event_date": event_date or date.today().isoformat(),
                "status": status,
                "score": score,
                "feedback": feedback,
            }
            if self._activity_history.empty:
                self._activity_history = pd.DataFrame([new_row])
            else:
                self._activity_history = pd.concat(
                    [self._activity_history, pd.DataFrame([new_row])],
                    ignore_index=True,
                )

    def get_company_skill_deficits(self) -> List[Dict[str, Any]]:
        """Calculates aggregated skill gaps across all employees for their target grades."""
        with self.lock:
            deficit_map: Dict[str, Dict[str, Any]] = {}
            for emp in self._employees.values():
                reqs = self.get_grade_requirements(emp.current_role, emp.target_grade)
                for skill, required_level in reqs.items():
                    current = emp.skills.get(skill, 0)
                    gap = max(0, required_level - current)
                    if gap > 0:
                        if skill not in deficit_map:
                            deficit_map[skill] = {
                                "skill": skill,
                                "total_gap": 0,
                                "affected_employees_count": 0,
                                "avg_gap": 0.0,
                            }
                        deficit_map[skill]["total_gap"] += gap
                        deficit_map[skill]["affected_employees_count"] += 1

            for item in deficit_map.values():
                if item["affected_employees_count"] > 0:
                    item["avg_gap"] = round(item["total_gap"] / item["affected_employees_count"], 2)

            sorted_deficits = sorted(
                deficit_map.values(), key=lambda x: (x["total_gap"], x["affected_employees_count"]), reverse=True
            )
            return sorted_deficits[:5]

    def get_risk_group_employees(self) -> List[Dict[str, Any]]:
        """Identifies employees with low engagement (high skip rate or large unresolved skill deficit)."""
        with self.lock:
            risk_list = []
            for emp in self._employees.values():
                history = self.get_employee_history(emp.id)
                skipped_count = 0
                completed_count = 0
                if not history.empty and "status" in history.columns:
                    skipped_count = int((history["status"] == "skipped").sum())
                    completed_count = int((history["status"] == "completed").sum())

                reqs = self.get_grade_requirements(emp.current_role, emp.target_grade)
                total_gap = sum(max(0, req_lvl - emp.skills.get(sk, 0)) for sk, req_lvl in reqs.items())

                # Risk criteria: >= 2 skips OR total gap >= 4 with low completion
                is_risk = (skipped_count >= 2) or (total_gap >= 4 and completed_count == 0)
                if is_risk:
                    risk_list.append({
                        "employee_id": emp.id,
                        "name": emp.name,
                        "current_role": emp.current_role,
                        "current_grade": emp.current_grade,
                        "target_grade": emp.target_grade,
                        "skipped_events": skipped_count,
                        "completed_events": completed_count,
                        "total_skill_gap": total_gap,
                        "risk_reason": (
                            "Высокая доля пропусков обучающих мероприятий"
                            if skipped_count >= 2
                            else "Критический дефицит навыков до следующего грейда без активности"
                        ),
                    })
            return risk_list

    def get_stats(self) -> Dict[str, Any]:
        """Returns dataset status summary for health check and diagnostics."""
        with self.lock:
            return {
                "initialized": self._initialized,
                "data_dir": str(self.data_dir),
                "total_employees": len(self._employees),
                "baseline_employees": len(self._employees) - len(self._custom_profiles),
                "custom_jury_profiles": len(self._custom_profiles),
                "total_events": len(self._events),
                "total_skills": len(self._skills_catalog),
                "history_records": len(self._activity_history),
            }


# ==============================================================================
# Global Thread-Safe Singleton
# ==============================================================================

_data_loader_instance: Optional[DataLoader] = None
_instance_lock = RLock()


def get_data_loader(data_dir: Optional[Union[str, Path]] = None) -> DataLoader:
    """Thread-safe accessor for global DataLoader singleton."""
    global _data_loader_instance
    with _instance_lock:
        if _data_loader_instance is None:
            _data_loader_instance = DataLoader(data_dir=data_dir)
            _data_loader_instance.load_all()
        return _data_loader_instance
