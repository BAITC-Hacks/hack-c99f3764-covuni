"""
Data Loader & In-Memory Cache Module
Halyk Bank — Career Quest (HackAlem AI)
Team 202453

Parses, validates, and caches the 4 foundational datasets:
- employees.json (200 profiles with role, grade, career_goal, skills 0-5)
- events.json (40 events with develops_skills, prerequisites, upcoming_sessions, mandatory)
- skills.json (60 skills and role_profiles with required_skills & critical_skills)
- activity_history.csv (2743 records with status: completed, dropped, no_show, etc.)

Snapshot Date: 2026-10-01
Provides thread-safe dynamic ingestion of jury verification profiles without server restarts.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("career_quest.data_loader")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

SNAPSHOT_DATE = "2026-10-01"
GRADE_ORDER = ["Junior", "Middle", "Senior", "Lead"]


# ==============================================================================
# Pydantic Data Models & Validation Schemas
# ==============================================================================

class SkillDefinition(BaseModel):
    skill_id: str
    name: str
    type: Optional[str] = "hard"
    category: Optional[str] = "engineering"
    description: Optional[str] = ""


class DevelopsSkillItem(BaseModel):
    skill_id: str
    gain: int = 1
    max_level: int = 5


class EventItem(BaseModel):
    event_id: str
    title: str
    description: Optional[str] = ""
    type: Optional[str] = "course"
    format: str = "online"  # online, offline, self_paced
    duration_hours: float = 0.0
    mandatory: bool = False
    target_roles: List[str] = Field(default_factory=list)
    target_grades: List[str] = Field(default_factory=list)
    develops_skills: List[DevelopsSkillItem] = Field(default_factory=list)
    prerequisites: Dict[str, int] = Field(default_factory=dict)
    upcoming_sessions: List[str] = Field(default_factory=list)

    # Compatibility properties
    @property
    def id(self) -> str:
        return self.event_id

    @property
    def target_skills(self) -> List[str]:
        return [dev.skill_id for dev in self.develops_skills]

    @property
    def skill_gain(self) -> int:
        return self.develops_skills[0].gain if self.develops_skills else 1


class CareerGoal(BaseModel):
    target_role: Optional[str] = None
    target_grade: Optional[str] = None


class EmployeeProfile(BaseModel):
    employee_id: str
    full_name: str
    department: Optional[str] = ""
    role: str
    grade: str
    manager_id: Optional[str] = None
    hire_date: Optional[str] = None
    tenure_months: Optional[int] = 0
    work_format: Optional[str] = "office"
    preferred_language: Optional[str] = "ru"
    career_goal: Optional[CareerGoal] = None
    skills: Dict[str, int] = Field(default_factory=dict)
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict)
    last_review_date: Optional[str] = None
    is_custom: bool = False

    # Normalized Accessors for Backward/Forward Compatibility
    @property
    def id(self) -> str:
        return self.employee_id

    @property
    def name(self) -> str:
        return self.full_name

    @property
    def current_role(self) -> str:
        return self.role

    @property
    def current_grade(self) -> str:
        return self.grade

    @property
    def target_grade(self) -> str:
        if self.career_goal and self.career_goal.target_grade:
            return self.career_goal.target_grade
        if self.grade in GRADE_ORDER:
            idx = GRADE_ORDER.index(self.grade)
            return GRADE_ORDER[min(idx + 1, len(GRADE_ORDER) - 1)]
        return "Senior"

    @property
    def target_role(self) -> str:
        if self.career_goal and self.career_goal.target_role:
            return self.career_goal.target_role
        return self.role


class CustomProfileUploadRequest(BaseModel):
    profiles: List[Dict[str, Any]] = Field(
        ...,
        description="List of candidate profiles for evaluation and verification."
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
        
        # Skill ID <-> Name bidirectional index
        self._skill_id_to_name: Dict[str, str] = {}
        self._skill_name_to_id: Dict[str, str] = {}
        
        # Role Profiles index: (role, grade) -> {required_skills, critical_skills}
        self._role_profiles: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._grade_requirements: Dict[str, Dict[str, Dict[str, int]]] = {}
        self._critical_skills_map: Dict[Tuple[str, str], List[str]] = {}

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
                # Support both skill_id and id
                sk_id = item.get("skill_id") or item.get("id") or item.get("name")
                name = item.get("name", sk_id)
                skill_obj = SkillDefinition(
                    skill_id=sk_id,
                    name=name,
                    type=item.get("type", "hard"),
                    category=item.get("category", "engineering"),
                    description=item.get("description", ""),
                )
                self._skills_catalog[sk_id] = skill_obj
                self._skill_id_to_name[sk_id] = name
                self._skill_name_to_id[name.lower()] = sk_id
                self._skill_name_to_id[sk_id.lower()] = sk_id

            # Additional common tech aliases for jury and candidate compatibility
            common_aliases = {
                "system design": "SK_SYSTEM_DESIGN",
                "python": "SK_PYTHON",
                "sql": "SK_SQL",
                "postgres": "SK_SQL",
                "postgresql": "SK_SQL",
                "mysql": "SK_SQL",
                "fastapi": "SK_PYTHON",
                "django": "SK_PYTHON",
                "docker": "SK_CONTAINERS",
                "kubernetes": "SK_CONTAINERS",
                "k8s": "SK_CONTAINERS",
                "containers": "SK_CONTAINERS",
                "aws": "SK_CLOUD",
                "cloud": "SK_CLOUD",
                "ci/cd": "SK_CICD",
                "cicd": "SK_CICD",
                "api design": "SK_API_DESIGN",
                "public speaking": "SK_PUBLIC_SPEAKING",
                "communication": "SK_COMMUNICATION",
                "machine learning": "SK_ML_BASICS",
                "ml": "SK_ML_BASICS",
                "deep learning": "SK_ML_BASICS",
                "mlops": "SK_CICD",
                "javascript": "SK_JAVASCRIPT",
                "typescript": "SK_TYPESCRIPT",
                "react": "SK_REACT",
                "statistics": "SK_STATISTICS",
                "data visualization": "SK_DATA_VIZ",
            }
            for alias, target_sk in common_aliases.items():
                if alias not in self._skill_name_to_id:
                    self._skill_name_to_id[alias] = target_sk

            # Parse role_profiles
            raw_profiles = data.get("role_profiles", [])
            if isinstance(raw_profiles, list):
                for rp in raw_profiles:
                    role = rp.get("role", "")
                    grade = rp.get("grade", "")
                    reqs = rp.get("required_skills", {})
                    crits = rp.get("critical_skills", [])
                    key = (role, grade)
                    self._role_profiles[key] = {
                        "required_skills": reqs,
                        "critical_skills": crits,
                    }
                    if role not in self._grade_requirements:
                        self._grade_requirements[role] = {}
                    self._grade_requirements[role][grade] = reqs
                    self._critical_skills_map[key] = crits

            logger.info(
                "Loaded %d skills and %d role_profiles from skills.json",
                len(self._skills_catalog),
                len(self._role_profiles)
            )
        except Exception as e:
            logger.error("Failed to parse skills.json: %s", e)

    def _load_events(self) -> None:
        events_path = self.data_dir / "events.json"
        if not events_path.exists():
            logger.warning("events.json not found at %s. Using empty registry.", events_path)
            return

        try:
            with open(events_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            raw_events = raw_data.get("events", []) if isinstance(raw_data, dict) else raw_data

            if isinstance(raw_events, list):
                for item in raw_events:
                    ev_id = item.get("event_id") or item.get("id")
                    
                    # Normalize develops_skills
                    dev_skills = []
                    if "develops_skills" in item:
                        for d in item["develops_skills"]:
                            dev_skills.append(DevelopsSkillItem(**d))
                    elif "target_skills" in item:
                        gain = item.get("skill_gain", 1)
                        for sk in item["target_skills"]:
                            sk_norm = self.normalize_skill_id(sk)
                            dev_skills.append(DevelopsSkillItem(skill_id=sk_norm, gain=gain, max_level=5))

                    event = EventItem(
                        event_id=ev_id,
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        type=item.get("type", "course"),
                        format=item.get("format", "online"),
                        duration_hours=float(item.get("duration_hours", 0.0)),
                        mandatory=bool(item.get("mandatory", False)),
                        target_roles=item.get("target_roles", []),
                        target_grades=item.get("target_grades", []),
                        develops_skills=dev_skills,
                        prerequisites=item.get("prerequisites", {}),
                        upcoming_sessions=item.get("upcoming_sessions", []),
                    )
                    self._events[event.event_id] = event
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
                raw_data = json.load(f)

            raw_emps = raw_data.get("employees", []) if isinstance(raw_data, dict) else raw_data

            if isinstance(raw_emps, list):
                for item in raw_emps:
                    emp = self._normalize_employee_dict(item, is_custom=False)
                    self._employees[emp.employee_id] = emp
            logger.info("Loaded %d baseline employees from employees.json", len(self._employees))
        except Exception as e:
            logger.error("Failed to parse employees.json: %s", e)

    def _normalize_employee_dict(self, d: Dict[str, Any], is_custom: bool = False) -> EmployeeProfile:
        """Normalizes both official dataset and jury custom profiles into uniform EmployeeProfile."""
        emp_id = str(d.get("employee_id") or d.get("id") or f"custom_{len(self._custom_profiles) + 1}")
        full_name = d.get("full_name") or d.get("name") or f"Candidate {emp_id}"
        role = d.get("role") or d.get("current_role") or "Backend Engineer"
        grade = d.get("grade") or d.get("current_grade") or "Middle"
        
        # Normalize career_goal
        career_goal = None
        if "career_goal" in d and isinstance(d["career_goal"], dict):
            career_goal = CareerGoal(**d["career_goal"])
        elif "target_grade" in d:
            target_role = d.get("target_role") or role
            career_goal = CareerGoal(target_role=target_role, target_grade=d["target_grade"])

        # Normalize skills dictionary keys to skill_id if possible
        raw_skills = d.get("skills", {})
        normalized_skills = {}
        for k, v in raw_skills.items():
            sk_id = self.normalize_skill_id(k)
            normalized_skills[sk_id] = int(v)

        return EmployeeProfile(
            employee_id=emp_id,
            full_name=full_name,
            department=d.get("department", ""),
            role=role,
            grade=grade,
            manager_id=d.get("manager_id"),
            hire_date=d.get("hire_date"),
            tenure_months=d.get("tenure_months", 0),
            work_format=d.get("work_format", "office"),
            preferred_language=d.get("preferred_language", "ru"),
            career_goal=career_goal,
            skills=normalized_skills,
            preferences=d.get("preferences", {}),
            last_review_date=d.get("last_review_date"),
            is_custom=is_custom,
        )

    def _load_activity_history(self) -> None:
        hist_path = self.data_dir / "activity_history.csv"
        if not hist_path.exists():
            logger.warning("activity_history.csv not found at %s. Using empty DataFrame.", hist_path)
            self._activity_history = pd.DataFrame(
                columns=["record_id", "employee_id", "event_id", "date", "status", "completion_pct", "feedback_rating"]
            )
            return

        try:
            df = pd.read_csv(hist_path)
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
        """Dynamically validates and loads jury verification profiles into in-memory cache without server restarts."""
        loaded: List[EmployeeProfile] = []
        errors: List[str] = []

        with self.lock:
            for idx, raw_profile in enumerate(profiles_data):
                try:
                    profile = self._normalize_employee_dict(raw_profile, is_custom=True)
                    self._employees[profile.employee_id] = profile
                    self._custom_profiles[profile.employee_id] = profile
                    loaded.append(profile)
                    logger.info("Dynamically ingested verification profile: %s (%s)", profile.employee_id, profile.full_name)
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
    # Accessors & Query Helpers for ML / Recommendation Engine
    # ==========================================================================

    def normalize_skill_id(self, skill_name_or_id: str) -> str:
        """Resolves human name or ID to canonical skill_id (e.g., 'System Design' -> 'SK_SYSTEM_DESIGN')."""
        if not skill_name_or_id:
            return ""
        norm_key = skill_name_or_id.strip().lower()
        if norm_key in self._skill_name_to_id:
            return self._skill_name_to_id[norm_key]
        return skill_name_or_id.strip()

    def get_skill_name(self, skill_id: str) -> str:
        """Returns human-readable name of skill (e.g., 'SK_SYSTEM_DESIGN' -> 'System Design')."""
        return self._skill_id_to_name.get(skill_id, skill_id)

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

    def normalize_role(self, role: str) -> str:
        """Normalizes role name to one of the 8 canonical role_profiles."""
        if not role:
            return "Backend Engineer"
        role_map = {
            "backend developer": "Backend Engineer",
            "backend dev": "Backend Engineer",
            "software engineer": "Backend Engineer",
            "frontend developer": "Frontend Engineer",
            "frontend dev": "Frontend Engineer",
            "data scientist": "Data Analyst",
            "data science": "Data Analyst",
            "bi analyst": "Data Analyst",
            "qa": "QA Engineer",
            "tester": "QA Engineer",
            "pm": "Product Manager",
            "hr": "HR Business Partner",
            "sales": "Sales Manager",
            "support": "Customer Support Specialist",
        }
        r_lower = role.strip().lower()
        if r_lower in role_map:
            return role_map[r_lower]
        for k, v in role_map.items():
            if k in r_lower or r_lower in k:
                return v
        return role.strip()

    def get_event(self, event_id: str) -> Optional[EventItem]:
        """Fetch a specific event by ID (case-insensitive fallback)."""
        with self.lock:
            key = str(event_id)
            if key in self._events:
                return self._events[key]
            for k, v in self._events.items():
                if k.lower() == key.lower():
                    return v
            return None

    def get_grade_requirements(self, role: str, target_grade: str) -> Dict[str, int]:
        """Returns required skills and minimum levels for a given role and grade."""
        with self.lock:
            norm_role = self.normalize_role(role)
            # Try exact key (norm_role, target_grade)
            rp = self._role_profiles.get((norm_role, target_grade))
            if rp and "required_skills" in rp:
                return rp["required_skills"]
            # Fallback to role alias (e.g. Backend Developer -> Backend Engineer)
            for (r, g), data in self._role_profiles.items():
                if g.lower() == target_grade.lower() and (r.lower() in norm_role.lower() or norm_role.lower() in r.lower()):
                    return data.get("required_skills", {})
            return {}

    def get_critical_skills(self, role: str, target_grade: str) -> List[str]:
        """Returns critical skills (must-have promotion blockers) for a given role and grade."""
        with self.lock:
            norm_role = self.normalize_role(role)
            rp = self._role_profiles.get((norm_role, target_grade))
            if rp and "critical_skills" in rp:
                return rp["critical_skills"]
            for (r, g), data in self._role_profiles.items():
                if g.lower() == target_grade.lower() and (r.lower() in norm_role.lower() or norm_role.lower() in r.lower()):
                    return data.get("critical_skills", [])
            return []

    def get_employee_history(self, employee_id: str) -> pd.DataFrame:
        """Returns historical participation logs for an employee."""
        with self.lock:
            if self._activity_history.empty or "employee_id" not in self._activity_history.columns:
                return pd.DataFrame()
            return self._activity_history[self._activity_history["employee_id"] == str(employee_id)].copy()

    def get_employee_format_stats(self, employee_id: str) -> Dict[str, Dict[str, int]]:
        """
        Calculates status counts (completed, dropped, no_show) grouped by event format (online, offline, self_paced).
        Used for behavioural format penalty calculation.
        """
        stats: Dict[str, Dict[str, int]] = {
            "online": {"completed": 0, "dropped": 0, "no_show": 0},
            "offline": {"completed": 0, "dropped": 0, "no_show": 0},
            "self_paced": {"completed": 0, "dropped": 0, "no_show": 0},
        }
        hist = self.get_employee_history(employee_id)
        if hist.empty:
            return stats

        for _, row in hist.iterrows():
            ev_id = str(row.get("event_id", ""))
            status = str(row.get("status", ""))
            event = self.get_event(ev_id)
            if event and event.format in stats:
                if status in stats[event.format]:
                    stats[event.format][status] += 1
                elif status == "skipped":
                    stats[event.format]["dropped"] += 1

        return stats

    def update_employee_skill(
        self, employee_id: str, skill_name_or_id: str, new_level: int
    ) -> Optional[EmployeeProfile]:
        """Updates a specific skill level for an employee in memory."""
        with self.lock:
            emp = self._employees.get(str(employee_id))
            if not emp:
                return None
            sk_id = self.normalize_skill_id(skill_name_or_id)
            emp.skills[sk_id] = new_level
            if str(employee_id) in self._custom_profiles:
                self._custom_profiles[str(employee_id)].skills[sk_id] = new_level
            return emp

    def record_activity(
        self,
        employee_id: str,
        event_id: str,
        status: str = "completed",
        score: float = 100.0,
        feedback: str = "Завершено через Career Quest",
        event_date: Optional[str] = None,
    ) -> None:
        """Appends a new participation record to activity history."""
        from datetime import date
        with self.lock:
            new_row = {
                "record_id": f"R_NEW_{len(self._activity_history) + 1}",
                "employee_id": str(employee_id),
                "event_id": str(event_id),
                "date": event_date or date.today().isoformat(),
                "status": status,
                "completion_pct": 100 if status == "completed" else 0,
                "score": score,
                "feedback_rating": 5.0,
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
                for skill_id, required_level in reqs.items():
                    current = emp.skills.get(skill_id, 0)
                    gap = max(0, required_level - current)
                    if gap > 0:
                        sk_name = self.get_skill_name(skill_id)
                        if sk_name not in deficit_map:
                            deficit_map[sk_name] = {
                                "skill": sk_name,
                                "skill_id": skill_id,
                                "total_gap": 0,
                                "affected_employees_count": 0,
                                "avg_gap": 0.0,
                            }
                        deficit_map[sk_name]["total_gap"] += gap
                        deficit_map[sk_name]["affected_employees_count"] += 1

            for item in deficit_map.values():
                if item["affected_employees_count"] > 0:
                    item["avg_gap"] = round(item["total_gap"] / item["affected_employees_count"], 2)

            sorted_deficits = sorted(
                deficit_map.values(), key=lambda x: (x["total_gap"], x["affected_employees_count"]), reverse=True
            )
            return sorted_deficits[:5]

    def get_risk_group_employees(self) -> List[Dict[str, Any]]:
        """Identifies employees with low engagement (frequent no_show/dropped or large unresolved gaps)."""
        with self.lock:
            risk_list = []
            for emp in self._employees.values():
                history = self.get_employee_history(emp.id)
                no_shows = 0
                dropped = 0
                completed = 0
                if not history.empty and "status" in history.columns:
                    no_shows = int((history["status"] == "no_show").sum())
                    dropped = int((history["status"] == "dropped").sum())
                    completed = int((history["status"] == "completed").sum())

                reqs = self.get_grade_requirements(emp.current_role, emp.target_grade)
                total_gap = sum(max(0, req_lvl - emp.skills.get(sk, 0)) for sk, req_lvl in reqs.items())

                # Risk criterion: >= 2 dropped/no_show or high gap without completions
                if (no_shows + dropped >= 2) or (total_gap >= 5 and completed == 0):
                    risk_list.append({
                        "employee_id": emp.employee_id,
                        "name": emp.full_name,
                        "current_role": emp.current_role,
                        "current_grade": emp.current_grade,
                        "target_grade": emp.target_grade,
                        "no_shows": no_shows,
                        "dropped": dropped,
                        "completed_events": completed,
                        "total_skill_gap": total_gap,
                        "risk_reason": (
                            f"Частые пропуски или прекращения курсов (пропусков: {no_shows}, брошено: {dropped})"
                            if (no_shows + dropped >= 2)
                            else "Критический дефицит навыков до следующего грейда без активности"
                        ),
                    })
            return risk_list

    def get_stats(self) -> Dict[str, Any]:
        """Returns dataset status summary for health check and diagnostics."""
        with self.lock:
            return {
                "initialized": self._initialized,
                "snapshot_date": SNAPSHOT_DATE,
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
