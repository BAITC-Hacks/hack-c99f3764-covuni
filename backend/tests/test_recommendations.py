"""
Automated Test Suite for Jury Criteria & Edge Cases
Halyk Bank — Career Quest (HackAlem AI)
Team 202453

Validates:
1. Jury Trap (Corner-case profile where naive single-factor rule fails)
2. Skill Progression & Ceiling Cap (min(current + gain, max_level))
3. Dynamic Jury JSON Profile Ingestion & Zero-Downtime Recommendation
4. HR Analytics & Risk Group Identification
"""

import pytest
from pathlib import Path
import sys

# Ensure backend root is on Python sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from data_loader import DataLoader, EmployeeProfile, EventItem
from main import (
    CompleteActivityRequest,
    RecommendationRequest,
    calculate_multi_factor_recommendations,
    complete_activity,
    get_data_loader,
    get_hr_analytics,
    get_recommendations,
    upload_custom_profiles,
    CustomProfileUploadRequest,
)


@pytest.fixture(scope="module")
def initialized_loader():
    """Provides the shared global instance of DataLoader."""
    data_dir = backend_dir.parent / "data"
    loader = get_data_loader(data_dir=data_dir)
    return loader


# ==============================================================================
# TEST 1: The Jury Corner-Case Trap (Failure of Naive Single-Factor Rule)
# ==============================================================================

def test_jury_corner_case_naive_rule_trap(initialized_loader: DataLoader):
    """
    JURY EDGE CASE CRITERION:
    Naive rule: Pick the skill with minimum level (Public Speaking = 1).
    Why it fails:
    - Target grade is Senior Backend Developer.
    - System Design is at level 2 (requires 4) -> HARD PROMOTION BLOCKER!
    - Public Speaking is at level 1, but is NOT required for Senior Backend promotion.
    - Furthermore, the candidate has skipped 3 soft-skill webinar trainings in history.

    EXPECTED RESULT:
    Multi-factor engine MUST recommend System Design (ev_001), NOT Public Speaking (ev_005)!
    """
    # 1. Ingest corner-case candidate
    candidate_id = "jury_trap_middle_candidate_001"
    raw_profile = {
        "id": candidate_id,
        "name": "Темирлан Бериков (Jury Corner Case)",
        "department": "Core Banking",
        "current_role": "Backend Developer",
        "current_grade": "Middle",
        "target_grade": "Senior",
        "skills": {
            "Python": 4,
            "PostgreSQL": 4,
            "FastAPI": 4,
            "Docker": 3,
            "System Design": 2,      # Level 2 -> Needs 4 for Senior (Gap: 2, CRITICAL BLOCKER)
            "Kubernetes": 3,
            "Public Speaking": 1,    # Level 1 (MINIMAL SKILL, but NOT a Senior requirement)
        },
        "preferences": {
            "preferred_formats": ["workshop"],
            "max_hours_per_week": 8,
        },
    }

    loaded_profiles, errors = initialized_loader.load_custom_profiles([raw_profile])
    assert len(loaded_profiles) == 1
    assert not errors

    # 2. Record 3 skipped soft-skill events in history for this employee
    initialized_loader.record_activity(candidate_id, "ev_005", status="skipped", score=0.0, feedback="Пропустил тренинг")
    initialized_loader.record_activity(candidate_id, "ev_past_soft_1", status="skipped", score=0.0, feedback="Не посетил")
    initialized_loader.record_activity(candidate_id, "ev_past_soft_2", status="skipped", score=0.0, feedback="Скипнул вебинар")

    # 3. Generate recommendations
    emp = initialized_loader.get_employee(candidate_id)
    recommendations = calculate_multi_factor_recommendations(emp, initialized_loader, max_recommendations=3)

    assert len(recommendations) > 0, "Recommendations list must not be empty"

    top_rec = recommendations[0]

    # Verify that the top recommendation targets System Design and NOT Public Speaking
    assert top_rec.target_skill == "System Design", (
        f"Multi-factor model must recommend 'System Design' to unblock Senior grade, "
        f"got '{top_rec.target_skill}' instead (naive single-factor trap!)."
    )
    assert top_rec.event_id == "ev_001"

    # Verify Public Speaking is penalized and is NOT the first choice
    rec_skills = [r.target_skill for r in recommendations]
    assert rec_skills[0] != "Public Speaking"

    # Verify explainable rationale mentions gap and grade blocker
    assert "System Design" in top_rec.rationale
    assert "Критический блокер грейда" in top_rec.rationale or "разрыв" in top_rec.rationale


# ==============================================================================
# TEST 2: Skill Progression Shift & Upper Ceiling Cap
# ==============================================================================

def test_skill_progress_shift_and_ceiling(initialized_loader: DataLoader):
    """
    CRITERION:
    When an employee completes an activity:
    - Skill increases by event.skill_gain: new_level = min(current + gain, max_level)
    - State updates in memory
    - Level does not exceed max_level (5)
    """
    test_emp_id = "emp_progression_test"
    raw_profile = {
        "id": test_emp_id,
        "name": "Айсулу Нурланова",
        "current_role": "Backend Developer",
        "current_grade": "Middle",
        "target_grade": "Senior",
        "skills": {
            "System Design": 2,
            "Kubernetes": 4,
        },
    }
    initialized_loader.load_custom_profiles([raw_profile])

    # 1. Complete event ev_001 (targets System Design and Kubernetes, gain = 1)
    req = CompleteActivityRequest(employee_id=test_emp_id, event_id="ev_001")
    resp = complete_activity(req)

    assert resp.status == "success"
    updated_emp = resp.employee

    # System Design was 2 -> should now be 3
    assert updated_emp.skills["System Design"] == 3
    # Kubernetes was 4 -> should now be 5
    assert updated_emp.skills["Kubernetes"] == 5

    # 2. Test Ceiling Cap: Complete again for Kubernetes (at 5)
    # Level must remain capped at max_level = 5
    resp2 = complete_activity(req)
    assert resp2.employee.skills["Kubernetes"] == 5


# ==============================================================================
# TEST 3: Dynamic Custom Profile Ingestion & Zero-Downtime Recommendation
# ==============================================================================

def test_dynamic_custom_jury_profile_upload_and_recommendation(initialized_loader: DataLoader):
    """
    CRITERION:
    Jury can upload arbitrary JSON profiles without server reboot.
    Uploaded profile is instantly available and evaluated by /api/recommendations.
    """
    custom_jury_id = "dynamic_jury_profile_xyz"
    upload_payload = CustomProfileUploadRequest(
        profiles=[
            {
                "id": custom_jury_id,
                "name": "Азамат Сериков (External Jury Profile)",
                "department": "Data Science",
                "current_role": "Data Scientist",
                "current_grade": "Junior",
                "target_grade": "Middle",
                "skills": {
                    "Python": 3,
                    "SQL": 2,
                    "Machine Learning": 1,   # Requires 3 for Middle DS
                    "Deep Learning": 1,      # Requires 2 for Middle DS
                    "MLOps": 1,              # Requires 2 for Middle DS
                },
                "preferences": {
                    "preferred_formats": ["hackathon"],
                },
            }
        ]
    )

    # Ingest profile
    upload_res = upload_custom_profiles(upload_payload)
    assert upload_res.status == "success"
    assert custom_jury_id in upload_res.profile_ids

    # Query recommendation endpoint directly
    rec_req = RecommendationRequest(employee_id=custom_jury_id)
    rec_res = get_recommendations(rec_req)

    assert rec_res.employee_id == custom_jury_id
    assert len(rec_res.recommendations) > 0
    # Best event should target Machine Learning / MLOps (e.g. ev_004 MLOps hackathon)
    top_skill = rec_res.recommendations[0].target_skill
    assert top_skill in ["MLOps", "Machine Learning", "Deep Learning"]


# ==============================================================================
# TEST 4: HR Analytics (Skills Deficit & Engagement Risk Group)
# ==============================================================================

def test_hr_analytics_aggregation(initialized_loader: DataLoader):
    """
    CRITERION:
    HR Analytics returns company-wide deficit skills and employees with low engagement.
    """
    analytics = get_hr_analytics()
    assert "top_deficit_skills" in analytics.model_dump()
    assert "risk_group" in analytics.model_dump()
    assert "summary" in analytics.model_dump()

    # Verify deficit list structure
    if analytics.top_deficit_skills:
        first = analytics.top_deficit_skills[0]
        assert "skill" in first
        assert "total_gap" in first
        assert first["total_gap"] >= 0
