"""
FastAPI Core Application
Halyk Bank — Career Quest (HackAlem AI)
Team 202453

Core Features:
- Explainable Multi-factor Recommendation Engine
- Dynamic In-Memory Data Store & Custom Jury Verification Profiles
- Skill Progression & Activity Completion Tracking
- HR Analytics (Skills Deficit & Engagement Risk Group)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from data_loader import (
    CustomProfileUploadRequest,
    CustomProfileUploadResponse,
    DataLoader,
    EmployeeProfile,
    EventItem,
    get_data_loader,
)

load_dotenv()
logger = logging.getLogger("career_quest.api")


# ==============================================================================
# Pydantic Schemas for Recommendations & Activities
# ==============================================================================

class RecommendationRequest(BaseModel):
    employee_id: Optional[str] = Field(None, description="Registered employee ID")
    profile: Optional[Dict[str, Any]] = Field(None, description="Ad-hoc candidate profile for direct scoring")


class RecommendationItem(BaseModel):
    event_id: str
    title: str
    target_skill: str
    gain: int
    max_level: int = 5
    score: float
    rationale: str


class RecommendationResponse(BaseModel):
    employee_id: str
    current_role: str
    current_grade: str
    target_grade: str
    recommendations: List[RecommendationItem]


class CompleteActivityRequest(BaseModel):
    employee_id: str
    event_id: str


class SkillProgressDiff(BaseModel):
    skill: str
    old_level: int
    new_level: int
    gain: int
    max_level: int = 5


class CompleteActivityResponse(BaseModel):
    status: str
    employee_id: str
    event_id: str
    skills_updated: List[SkillProgressDiff]
    employee: EmployeeProfile


class HRAnalyticsResponse(BaseModel):
    top_deficit_skills: List[Dict[str, Any]]
    risk_group: List[Dict[str, Any]]
    summary: Dict[str, Any]


# ==============================================================================
# Multi-Factor Scoring & Explainable Rationale Engine
# ==============================================================================

SNAPSHOT_DATE = "2026-10-01"


def get_emp_skill_level(emp: EmployeeProfile, loader: DataLoader, skill_id_or_name: str) -> int:
    """Safely retrieves skill level for an employee supporting both canonical IDs and human names."""
    norm_id = loader.normalize_skill_id(skill_id_or_name)
    sk_name = loader.get_skill_name(norm_id)
    if norm_id in emp.skills:
        return emp.skills[norm_id]
    if sk_name in emp.skills:
        return emp.skills[sk_name]
    if skill_id_or_name in emp.skills:
        return emp.skills[skill_id_or_name]
    norm_lower = norm_id.lower()
    for k, v in emp.skills.items():
        if k.lower() == norm_lower or k.lower() == sk_name.lower():
            return v
    return 0


def calculate_multi_factor_recommendations(
    emp: EmployeeProfile,
    loader: DataLoader,
    max_recommendations: int = 3,
) -> List[RecommendationItem]:
    """
    Computes explainable recommendations based on the 4 strict organizer rules:
    1. Snapshot Date (2026-10-01): Scheduled events must have upcoming sessions >= 2026-10-01.
    2. Strict Event Filtering:
       - Mandatory events (EV_001..EV_004) are excluded.
       - Events with 'completed' status in history are excluded (EXCEPT EV_036 Public Speaking Club).
       - Prerequisites check: if emp.skills[req_skill] < req_level, event is forbidden.
       - Ceiling check (max_level): if emp.skills[dev_skill] >= max_level for all developed skills, event is filtered out.
    3. Critical Skills Priority:
       - Role profiles target grade critical_skills get x2.5 multiplier as promotion blockers.
    4. Behavioral History Penalties:
       - Penalties for 'no_show' and 'dropped' statuses across formats (online, offline, self_paced).
    """
    events = loader.get_events()
    target_role = emp.target_role
    target_grade = emp.target_grade
    grade_reqs = loader.get_grade_requirements(target_role, target_grade)
    critical_skills = set(loader.get_critical_skills(target_role, target_grade))
    history = loader.get_employee_history(emp.id)

    # 1. Historical event status sets
    completed_events = set()
    dropped_events = set()
    no_show_events = set()
    if not history.empty and "status" in history.columns:
        completed_df = history[history["status"] == "completed"]
        if "event_id" in completed_df.columns:
            completed_events = set(completed_df["event_id"].astype(str).str.upper())

        dropped_df = history[history["status"].isin(["dropped", "skipped"])]
        if "event_id" in dropped_df.columns:
            dropped_events = set(dropped_df["event_id"].astype(str).str.upper())

        no_show_df = history[history["status"] == "no_show"]
        if "event_id" in no_show_df.columns:
            no_show_events = set(no_show_df["event_id"].astype(str).str.upper())

    # Format-level behavioral statistics
    format_stats = loader.get_employee_format_stats(emp.id)

    scored_candidates: List[RecommendationItem] = []

    for event in events:
        ev_id = event.event_id.upper()

        # Rule 2.1: Mandatory exclusion
        if event.mandatory or ev_id in {"EV_001", "EV_002", "EV_003", "EV_004"}:
            continue

        # Rule 2.2: Completed exclusion (EXCEPTION: EV_036 Public Speaking Club)
        if ev_id != "EV_036" and ev_id in completed_events:
            continue

        # Rule 2.3: Prerequisites check (emp.skill < min_level -> forbidden)
        prereq_failed = False
        for req_sk, min_lvl in event.prerequisites.items():
            emp_lvl = get_emp_skill_level(emp, loader, req_sk)
            if emp_lvl < min_lvl:
                prereq_failed = True
                break
        if prereq_failed:
            continue

        # Rule 1: Snapshot Date Check for Scheduled Events
        if event.format != "self_paced":
            future_sessions = [s for s in event.upcoming_sessions if s >= SNAPSHOT_DATE]
            if not future_sessions:
                continue

        # Rule 2.4: Ceiling Cap Check (max_level)
        # Event must provide positive gain for at least one skill
        valid_devs = []
        for dev in event.develops_skills:
            cur_lvl = get_emp_skill_level(emp, loader, dev.skill_id)
            if cur_lvl < dev.max_level:
                valid_devs.append((dev, cur_lvl))
        if not valid_devs:
            continue

        # Evaluate skills developed by this event
        best_dev = None
        best_skill_score = -1.0
        best_norm_sk = ""
        best_sk_name = ""
        best_cur_lvl = 0
        best_req_lvl = 0
        best_gap = 0
        best_is_critical = False
        synergy_score = 0.0

        for dev, cur_lvl in valid_devs:
            norm_sk = loader.normalize_skill_id(dev.skill_id)
            sk_name = loader.get_skill_name(norm_sk)
            req_lvl = grade_reqs.get(norm_sk, grade_reqs.get(sk_name, 0))
            gap = max(0, req_lvl - cur_lvl)
            eff_gain = min(dev.gain, dev.max_level - cur_lvl)

            is_crit = (norm_sk in critical_skills) or any(
                c.lower() in [norm_sk.lower(), sk_name.lower()] for c in critical_skills
            )

            # Rule 3: Priority of Critical Skills (x2.5 multiplier for promotion blocker)
            crit_mult = 2.5 if (is_crit and gap > 0) else 1.0
            crit_boost = 5.0 if (is_crit and gap > 0) else 0.0

            s_score = (gap * 3.0 * crit_mult) + crit_boost + (eff_gain * 2.0)

            if s_score > best_skill_score:
                if best_dev is not None:
                    synergy_score += 1.0  # Bonus for multi-skill development
                best_skill_score = s_score
                best_dev = dev
                best_norm_sk = norm_sk
                best_sk_name = sk_name
                best_cur_lvl = cur_lvl
                best_req_lvl = req_lvl
                best_gap = gap
                best_is_critical = is_crit
            else:
                synergy_score += 0.5

        # Rule 4: Behavioral History Penalties
        fmt = event.format
        fmt_data = format_stats.get(fmt, {})
        no_shows = fmt_data.get("no_show", 0)
        dropped = fmt_data.get("dropped", 0)

        history_multiplier = 1.0
        history_reasons = []

        if no_shows > 0:
            history_multiplier -= min(0.35, 0.15 * no_shows)
            history_reasons.append(f"{no_shows} неявка (no_show) в формате {fmt}")
        if dropped > 0:
            history_multiplier -= min(0.30, 0.10 * dropped)
            history_reasons.append(f"{dropped} прерванный курс (dropped) в формате {fmt}")

        if ev_id in dropped_events or ev_id in no_show_events:
            history_multiplier *= 0.5
            history_reasons.append("ранее пропущенное или брошенное мероприятие")

        history_multiplier = max(0.2, history_multiplier)

        # Event Fit & Efficiency
        efficiency = (event.skill_gain / max(event.duration_hours, 1.0)) * 2.0
        pref_formats = emp.preferences.get("preferred_formats", []) if emp.preferences else []
        if event.format in pref_formats:
            efficiency += 1.5

        total_score = round((best_skill_score + synergy_score + efficiency) * history_multiplier, 2)

        if total_score > 0.0:
            crit_text = (
                "Критический блокер грейда (мультипликатор x2.5)"
                if (best_is_critical and best_gap > 0)
                else ("Целевой навык грейда" if best_gap > 0 else "Дополнительное развитие")
            )
            hist_text = (
                f"Штраф истории: {', '.join(history_reasons)}"
                if history_reasons
                else f"Высокая вовлеченность (без штрафов в формате {fmt})"
            )

            rationale = (
                f"[Фактор 1: Дефицит] Навык '{best_sk_name}': текущий уровень {best_cur_lvl}, "
                f"требование для {target_grade}: {best_req_lvl} (разрыв: {best_gap}). "
                f"[Фактор 2: Критичность] {crit_text}. "
                f"[Фактор 3: История] {hist_text}. "
                f"[Фактор 4: Эффективность] Формат {fmt}, прирост +{best_dev.gain} (потолок: {best_dev.max_level}) за {event.duration_hours}ч."
            )

            scored_candidates.append(
                RecommendationItem(
                    event_id=event.event_id,
                    title=event.title,
                    target_skill=best_sk_name,
                    gain=best_dev.gain,
                    max_level=best_dev.max_level,
                    score=total_score,
                    rationale=rationale,
                )
            )

    scored_candidates.sort(key=lambda x: x.score, reverse=True)

    unique_recommendations: List[RecommendationItem] = []
    seen_events = set()
    for item in scored_candidates:
        if item.event_id not in seen_events:
            seen_events.add(item.event_id)
            unique_recommendations.append(item)
        if len(unique_recommendations) >= max_recommendations:
            break

    return enhance_with_llm_if_available(emp, unique_recommendations)


def enhance_with_llm_if_available(
    emp: EmployeeProfile, recommendations: List[RecommendationItem]
) -> List[RecommendationItem]:
    """Enhances deterministic rationale with OpenAI GPT-4o-mini if API key is valid."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("your_"):
        return recommendations

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=3.0)

        for rec in recommendations:
            prompt = (
                f"Сотрудник: {emp.name}, роль: {emp.current_role}, текущий грейд: {emp.current_grade}, "
                f"целевой грейд: {emp.target_grade}. Мероприятие: '{rec.title}', навык: '{rec.target_skill}', "
                f"базовое обоснование: '{rec.rationale}'.\n"
                f"Сформулируй краткое, убедительное объяснение (1-2 предложения) для сотрудника от лица Halyk Career AI, "
                f"почему именно этот шаг критически важен для повышения в грейде."
            )
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "Ты персональный карьерный ассистент Halyk Bank."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=100,
                temperature=0.3,
            )
            llm_text = response.choices[0].message.content.strip()
            if llm_text:
                rec.rationale = f"{llm_text} | {rec.rationale}"
    except Exception as e:
        logger.warning("LLM explanation enrichment skipped (using deterministic fallback): %s", e)

    return recommendations


# ==============================================================================
# FastAPI Application & Lifespan
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    loader = get_data_loader()
    yield


app = FastAPI(
    title="Halyk Bank — Career Quest API",
    description="Explainable Multi-factor Career & Upskilling Recommendation Engine (Team 202453)",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
if not origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Core API Endpoints
# ==============================================================================

@app.get("/health", summary="Healthcheck & Dataset Status")
def healthcheck() -> Dict[str, Any]:
    loader = get_data_loader()
    stats = loader.get_stats()
    openai_key_configured = bool(
        os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY", "").startswith("your_")
    )
    return {
        "status": "healthy",
        "team_id": "202453",
        "project": "Halyk Bank Career Quest",
        "llm_ready": openai_key_configured,
        "dataset_stats": stats,
    }


@app.get("/api/profiles", response_model=List[EmployeeProfile], summary="List all employee profiles")
def list_profiles(include_custom: bool = True) -> List[EmployeeProfile]:
    loader = get_data_loader()
    return loader.get_all_employees(include_custom=include_custom)


@app.get("/api/profiles/{employee_id}", response_model=EmployeeProfile, summary="Get employee profile by ID")
def get_profile(employee_id: str) -> EmployeeProfile:
    loader = get_data_loader()
    profile = loader.get_employee(employee_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Employee profile '{employee_id}' not found")
    return profile


@app.post(
    "/api/profiles/upload",
    response_model=CustomProfileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload custom jury verification profiles (JSON body)",
)
def upload_custom_profiles(payload: CustomProfileUploadRequest) -> CustomProfileUploadResponse:
    loader = get_data_loader()
    loaded, errors = loader.load_custom_profiles(payload.profiles)
    return CustomProfileUploadResponse(
        status="success" if loaded else "failed",
        loaded_count=len(loaded),
        profile_ids=[p.id for p in loaded],
        validation_errors=errors,
    )


@app.post(
    "/api/profiles/upload-file",
    response_model=CustomProfileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload custom jury verification profiles (JSON file upload)",
)
async def upload_custom_profiles_file(file: UploadFile = File(...)) -> CustomProfileUploadResponse:
    import json
    try:
        content = await file.read()
        parsed = json.loads(content.decode("utf-8"))
        profiles = parsed if isinstance(parsed, list) else [parsed]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {str(e)}")

    loader = get_data_loader()
    loaded, errors = loader.load_custom_profiles(profiles)
    return CustomProfileUploadResponse(
        status="success" if loaded else "failed",
        loaded_count=len(loaded),
        profile_ids=[p.id for p in loaded],
        validation_errors=errors,
    )


@app.post(
    "/api/recommendations",
    response_model=RecommendationResponse,
    summary="Get explainable multi-factor upskilling recommendations",
)
def get_recommendations(req: RecommendationRequest) -> RecommendationResponse:
    """
    Evaluates employee against 4-factor scoring model:
    - Skill deficit to target grade
    - Promotion criticality
    - Historical participation and fatigue
    - Event efficiency and format fit
    """
    loader = get_data_loader()
    target_emp: Optional[EmployeeProfile] = None

    if req.employee_id:
        target_emp = loader.get_employee(req.employee_id)
        if not target_emp:
            raise HTTPException(status_code=404, detail=f"Employee '{req.employee_id}' not found")
    elif req.profile:
        # Dynamic profile evaluation
        loaded, _ = loader.load_custom_profiles([req.profile])
        if loaded:
            target_emp = loaded[0]

    if not target_emp:
        raise HTTPException(
            status_code=400,
            detail="Either 'employee_id' or a valid 'profile' object must be provided in request body"
        )

    recommendations = calculate_multi_factor_recommendations(target_emp, loader, max_recommendations=3)

    return RecommendationResponse(
        employee_id=target_emp.id,
        current_role=target_emp.current_role,
        current_grade=target_emp.current_grade,
        target_grade=target_emp.target_grade,
        recommendations=recommendations,
    )


@app.post(
    "/api/activities/complete",
    response_model=CompleteActivityResponse,
    summary="Record event completion and advance employee skills",
)
def complete_activity(req: CompleteActivityRequest) -> CompleteActivityResponse:
    """
    Applies skill progression rule: new_level = min(current_level + gain, max_level).
    Updates state in in-memory store and appends to activity history.
    """
    loader = get_data_loader()
    emp = loader.get_employee(req.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail=f"Employee '{req.employee_id}' not found")

    event = loader.get_event(req.event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{req.event_id}' not found")

    skills_updated: List[SkillProgressDiff] = []

    develops = event.develops_skills
    if not develops and event.target_skills:
        from data_loader import DevelopsSkillItem
        develops = [
            DevelopsSkillItem(skill_id=loader.normalize_skill_id(s), gain=event.skill_gain, max_level=5)
            for s in event.target_skills
        ]

    for dev in develops:
        sk_id = dev.skill_id
        sk_name = loader.get_skill_name(sk_id)
        current_level = get_emp_skill_level(emp, loader, sk_id)
        new_level = min(current_level + dev.gain, dev.max_level)
        gain = new_level - current_level
        loader.update_employee_skill(emp.id, sk_id, new_level)
        if sk_name != sk_id and sk_name in emp.skills:
            emp.skills[sk_name] = new_level

        skills_updated.append(
            SkillProgressDiff(
                skill=sk_name,
                old_level=current_level,
                new_level=new_level,
                gain=gain,
                max_level=dev.max_level,
            )
        )

    # Record completion in activity history
    loader.record_activity(
        employee_id=emp.id,
        event_id=event.event_id,
        status="completed",
        score=100.0,
        feedback=f"Успешное завершение курса '{event.title}'",
        event_date=SNAPSHOT_DATE,
    )

    updated_emp = loader.get_employee(emp.id)
    return CompleteActivityResponse(
        status="success",
        employee_id=emp.id,
        event_id=event.event_id,
        skills_updated=skills_updated,
        employee=updated_emp,
    )


@app.get("/api/hr/analytics", response_model=HRAnalyticsResponse, summary="Get company-wide HR upskilling analytics")
def get_hr_analytics() -> HRAnalyticsResponse:
    """Returns top 5 deficit skills across the organization and employees requiring engagement attention."""
    loader = get_data_loader()
    top_deficits = loader.get_company_skill_deficits()
    risk_group = loader.get_risk_group_employees()
    all_employees = loader.get_all_employees()

    return HRAnalyticsResponse(
        top_deficit_skills=top_deficits,
        risk_group=risk_group,
        summary={
            "total_employees": len(all_employees),
            "risk_group_count": len(risk_group),
            "deficit_skills_count": len(top_deficits),
        },
    )


@app.get("/api/events", summary="List all upskilling events")
def list_events():
    loader = get_data_loader()
    return loader.get_events()


@app.get("/api/skills", summary="Get skills catalog and grade matrix")
def get_skills_matrix():
    loader = get_data_loader()
    return {
        "skills": list(loader._skills_catalog.values()),
        "grade_requirements": loader._grade_requirements,
    }
