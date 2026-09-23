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

def calculate_multi_factor_recommendations(
    emp: EmployeeProfile,
    loader: DataLoader,
    max_recommendations: int = 3,
) -> List[RecommendationItem]:
    """
    Computes explainable recommendations based on the 4-factor scoring model:
    1. Skill Deficit (gap between target grade requirement and current level)
    2. Promotion Criticality (core technical skills required for promotion have 2.5x multiplier)
    3. Behavioral History & Fatigue (penalties for skipped formats/events, bonuses for high ratings)
    4. Event Fit & Efficiency (gain per hour, format affinity)
    """
    events = loader.get_events()
    grade_reqs = loader.get_grade_requirements(emp.current_role, emp.target_grade)
    history = loader.get_employee_history(emp.id)

    # Extract historical behavioral patterns
    skipped_events = set()
    skipped_formats = set()
    if not history.empty and "status" in history.columns:
        skipped_df = history[history["status"] == "skipped"]
        if "event_id" in skipped_df.columns:
            skipped_events = set(skipped_df["event_id"].astype(str))

    scored_candidates = []

    for event in events:
        # Check target skills of the event
        for target_skill in event.target_skills:
            current_level = emp.skills.get(target_skill, 0)
            required_level = grade_reqs.get(target_skill, 0)

            # Factor 1: Skill Deficit (S_gap)
            skill_gap = max(0, required_level - current_level)

            # Factor 2: Promotion Criticality (W_crit)
            # If skill is not required for next grade promotion, weight is 0.0
            is_grade_requirement = target_skill in grade_reqs
            promotion_weight = 2.5 if (is_grade_requirement and skill_gap > 0) else 0.1

            # Factor 3: History & Engagement Penalty/Bonus (H_history)
            history_multiplier = 1.0
            history_reasons = []

            # Check if this exact event or skill format was repeatedly skipped
            if event.id in skipped_events:
                history_multiplier *= 0.3
                history_reasons.append("ранее пропущенное мероприятие")

            # Check if format has high skip rate in history
            if not history.empty and "status" in history.columns:
                user_skips_for_format = 0
                for _, row in history.iterrows():
                    hist_ev = loader.get_event(str(row.get("event_id", "")))
                    if hist_ev and hist_ev.format == event.format and row.get("status") == "skipped":
                        user_skips_for_format += 1
                
                if user_skips_for_format >= 2:
                    history_multiplier *= 0.4
                    history_reasons.append(f"низкая вовлеченность в формат {event.format} (пропусков: {user_skips_for_format})")

            # Factor 4: Event Fit & Efficiency (E_fit)
            efficiency = (event.skill_gain / max(event.duration_hours, 1.0)) * 2.0
            pref_formats = emp.preferences.get("preferred_formats", []) if emp.preferences else []
            if event.format in pref_formats:
                efficiency += 1.0

            # Composite Score Formula
            base_score = (skill_gap * 3.0) + (promotion_weight * 2.0) + efficiency
            total_score = round(base_score * history_multiplier, 2)

            # Only consider events with meaningful positive score
            if total_score > 0.5:
                # Deterministic Explainable Rationale
                crit_desc = "Критический блокер грейда" if (is_grade_requirement and skill_gap > 0) else "Дополнительный развивающий навык"
                hist_desc = (
                    f"Штраф истории: {', '.join(history_reasons)}"
                    if history_reasons
                    else "Высокая готовность к участию (без пропусков в истории)"
                )

                rationale = (
                    f"[Фактор 1: Дефицит] Текущий уровень '{target_skill}': {current_level}, "
                    f"требование для {emp.target_grade}: {required_level} (разрыв: {skill_gap}). "
                    f"[Фактор 2: Критичность] {crit_desc}. "
                    f"[Фактор 3: История] {hist_desc}. "
                    f"[Фактор 4: Эффективность] Формат {event.format} (+{event.skill_gain} за {event.duration_hours}ч)."
                )

                scored_candidates.append(
                    RecommendationItem(
                        event_id=event.id,
                        title=event.title,
                        target_skill=target_skill,
                        gain=event.skill_gain,
                        max_level=5,
                        score=total_score,
                        rationale=rationale,
                    )
                )

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x.score, reverse=True)

    # Remove duplicates for the same event
    unique_recommendations: List[RecommendationItem] = []
    seen_events = set()
    for item in scored_candidates:
        if item.event_id not in seen_events:
            seen_events.add(item.event_id)
            unique_recommendations.append(item)
        if len(unique_recommendations) >= max_recommendations:
            break

    # Attempt LLM-enhancement if API key is provided, otherwise return deterministic rationale
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
    max_level = 5

    for skill in event.target_skills:
        current_level = emp.skills.get(skill, 0)
        new_level = min(current_level + event.skill_gain, max_level)
        gain = new_level - current_level
        loader.update_employee_skill(emp.id, skill, new_level)
        skills_updated.append(
            SkillProgressDiff(
                skill=skill,
                old_level=current_level,
                new_level=new_level,
                gain=gain,
                max_level=max_level,
            )
        )

    # Record completion in activity history
    loader.record_activity(
        employee_id=emp.id,
        event_id=event.id,
        status="completed",
        score=5.0,
        feedback=f"Успешное завершение курса '{event.title}'",
    )

    updated_emp = loader.get_employee(emp.id)
    return CompleteActivityResponse(
        status="success",
        employee_id=emp.id,
        event_id=event.id,
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
