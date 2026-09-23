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

import json
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


class LLMRationaleItem(BaseModel):
    """One validated explanation returned by the language model."""

    event_id: str
    rationale: str = Field(min_length=20, max_length=1200)


class LLMRationaleResponse(BaseModel):
    """Structured OpenAI response for all selected recommendations."""

    recommendations: List[LLMRationaleItem] = Field(min_length=1, max_length=3)


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

    return unique_recommendations


def build_verified_factor_summary(
    language: str,
    *,
    target_role: str,
    target_grade: str,
    skill: str,
    current_level: int,
    required_level: int,
    gap: int,
    is_critical: bool,
    gain: int,
    projected_level: int,
    max_level: int,
    event_format: str,
    format_history: Dict[str, int],
    format_is_preferred: bool,
) -> str:
    """Builds a localized, fully verified four-factor explanation."""
    completed = format_history.get("completed", 0)
    no_show = format_history.get("no_show", 0)
    dropped = format_history.get("dropped", 0)

    if language == "en":
        criticality = "is a critical promotion skill" if is_critical else "supports the promotion profile"
        preference = "; this is a preferred format" if format_is_preferred else ""
        return (
            f"Verified factors: for {target_grade} {target_role}, {skill} {criticality}: "
            f"current level {current_level}, required {required_level}, gap {gap}. "
            f"The activity adds +{gain}, reaching {projected_level} with a maximum of {max_level}; "
            f"{event_format} history: {completed} completed, {no_show} no-shows, {dropped} dropped{preference}."
        )

    if language == "kk":
        criticality = "шешуші дағды" if is_critical else "мансаптық өсуге қажет дағды"
        preference = "; бұл қызметкердің таңдаулы форматы" if format_is_preferred else ""
        return (
            f"Тексерілген факторлар: {target_grade} {target_role} деңгейіне өту үшін {skill} — {criticality}; "
            f"қазіргі деңгей {current_level}, талап {required_level}, алшақтық {gap}. "
            f"Белсенділік +{gain} қосып, деңгейді {projected_level}-ке жеткізеді (ең көбі {max_level}); "
            f"{event_format} тарихы: аяқталғаны {completed}, келмегені {no_show}, тоқтатылғаны {dropped}{preference}."
        )

    criticality = "критически важен для повышения" if is_critical else "поддерживает профиль повышения"
    preference = "; это предпочтительный формат сотрудника" if format_is_preferred else ""
    return (
        f"Проверенные факторы: для перехода на {target_grade} {target_role} навык {skill} "
        f"{criticality}: текущий уровень {current_level}, требуется {required_level}, разрыв {gap}. "
        f"Активность даст +{gain}, повысив уровень до {projected_level} при максимуме {max_level}; "
        f"история формата {event_format}: завершено {completed}, неявок {no_show}, прервано {dropped}{preference}."
    )


def enhance_with_llm_if_available(
    emp: EmployeeProfile,
    recommendations: List[RecommendationItem],
    loader: DataLoader,
) -> List[RecommendationItem]:
    """Enriches all selected recommendations in one bounded OpenAI request.

    The deterministic rationales remain the source of truth and are returned
    unchanged whenever the API key is missing, OpenAI is unavailable, the
    request exceeds the timeout, or the structured response is incomplete.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not recommendations or not api_key or api_key.startswith("your_"):
        return recommendations

    try:
        from openai import OpenAI

        preferred_language = (emp.preferred_language or "ru").lower()
        if preferred_language not in {"ru", "kk", "en"}:
            preferred_language = "ru"
        language_rule = {
            "ru": "ОБЯЗАТЕЛЬНО: напиши rationale только на русском языке.",
            "kk": "МІНДЕТТІ ТҮРДЕ: rationale мәтінін тек қазақ тілінде жаз; орыс және ағылшын тілдерін қолданба.",
            "en": "MANDATORY: write the rationale only in English.",
        }[preferred_language]

        grade_requirements = loader.get_grade_requirements(emp.target_role, emp.target_grade)
        critical_skills = set(loader.get_critical_skills(emp.target_role, emp.target_grade))
        format_stats = loader.get_employee_format_stats(emp.id)
        preferred_formats = (
            emp.preferences.get("preferred_formats", []) if emp.preferences else []
        )

        candidate_context: List[Dict[str, Any]] = []
        verified_summary_by_event: Dict[str, str] = {}
        for rec in recommendations:
            event = loader.get_event(rec.event_id)
            event_format = event.format if event else "unknown"
            normalized_skill = loader.normalize_skill_id(rec.target_skill)
            current_level = get_emp_skill_level(emp, loader, normalized_skill)
            required_level = grade_requirements.get(
                normalized_skill,
                grade_requirements.get(rec.target_skill, 0),
            )
            is_critical = normalized_skill in critical_skills or any(
                str(skill).lower() in {
                    normalized_skill.lower(),
                    rec.target_skill.lower(),
                }
                for skill in critical_skills
            )

            format_history = format_stats.get(event_format, {})
            format_is_preferred = event_format in preferred_formats
            projected_level = min(current_level + rec.gain, rec.max_level)
            candidate_context.append(
                {
                    "event_id": rec.event_id,
                    "title": rec.title,
                    "target_skill": rec.target_skill,
                    "current_level": current_level,
                    "required_level_for_target_grade": required_level,
                    "skill_gap": max(0, required_level - current_level),
                    "critical_for_target_grade": is_critical,
                    "format": event_format,
                    "duration_hours": event.duration_hours if event else None,
                    "format_is_preferred": format_is_preferred,
                    "history_for_this_format": format_history,
                    "gain": rec.gain,
                    "max_level": rec.max_level,
                    "projected_level": projected_level,
                    "deterministic_score": rec.score,
                }
            )
            verified_summary_by_event[rec.event_id] = build_verified_factor_summary(
                preferred_language,
                target_role=emp.target_role,
                target_grade=emp.target_grade,
                skill=rec.target_skill,
                current_level=current_level,
                required_level=required_level,
                gap=max(0, required_level - current_level),
                is_critical=is_critical,
                gain=rec.gain,
                projected_level=projected_level,
                max_level=rec.max_level,
                event_format=event_format,
                format_history=format_history,
                format_is_preferred=format_is_preferred,
            )

        system_prompt = (
            f"{language_rule} "
            "You are Halyk Career AI, a careful career coach. Produce one personalized "
            "rationale for every supplied recommendation and keep the same event_id values. "
            "Write only in the employee's preferred language: ru means Russian, kk means "
            "Kazakh, en means English. Each rationale must be exactly one natural motivational "
            "sentence of no more than 35 words. Explain why this activity and format are a good "
            "next step given the target grade, skill gap, promotion criticality, and history. "
            "Praise successful participation when completed is positive, "
            "and gently warn against another missed or dropped activity when those counts are "
            "positive. If history is empty, say there is no negative history for the format. "
            "Never invent facts, events, levels, dates, or history. Do not use markdown and "
            "do not expose scoring formulas or internal field names. "
            f"{language_rule}"
        )
        user_context = {
            "employee": {
                "name": emp.name,
                "current_role": emp.current_role,
                "current_grade": emp.current_grade,
                "target_role": emp.target_role,
                "target_grade": emp.target_grade,
                "preferred_language": preferred_language,
                "mandatory_language_rule": language_rule,
                "preferred_formats": preferred_formats,
            },
            "recommendations": candidate_context,
        }

        # One call for all 1-3 cards keeps latency and token usage predictable.
        client = OpenAI(api_key=api_key, timeout=4.5, max_retries=0)
        completion = client.chat.completions.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_context, ensure_ascii=False),
                },
            ],
            response_format=LLMRationaleResponse,
            max_tokens=350,
            temperature=0.25,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI returned no parsed recommendation payload")

        expected_ids = [rec.event_id for rec in recommendations]
        returned_ids = [item.event_id for item in parsed.recommendations]
        if len(returned_ids) != len(set(returned_ids)) or set(returned_ids) != set(expected_ids):
            raise ValueError("OpenAI returned incomplete or unexpected event IDs")

        rationale_by_event = {
            item.event_id: item.rationale.strip() for item in parsed.recommendations
        }
        if any(not rationale_by_event[event_id] for event_id in expected_ids):
            raise ValueError("OpenAI returned an empty rationale")

        for rec in recommendations:
            rec.rationale = (
                f"{rationale_by_event[rec.event_id]} "
                f"{verified_summary_by_event[rec.event_id]}"
            )
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
    recommendations = enhance_with_llm_if_available(target_emp, recommendations, loader)

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


