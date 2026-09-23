"""
Automated Test Suite for Jury Criteria, Organizer Specifications & Edge Cases
Halyk Bank — Career Quest (HackAlem AI)
Team 202453

Validates:
1. Real Dataset: Employee E0001 (Junior -> Middle Backend, critical API Design blocker, EV_005)
2. Real Dataset: Employee E0028 (Middle -> Senior Backend, EV_006/EV_007 excluded as completed, EV_005 top rec)
3. Strict Mandatory Events Exclusion (EV_001 - EV_004 never recommended)
4. EV_036 (Public Speaking Club) Repeatable Exception
5. Prerequisites Strict Filtering (prerequisites threshold enforcement)
6. Upper Ceiling Cap Filtering (no gain above max_level)
7. Jury Trap (Corner-case profile where naive single-factor rule fails)
8. Skill Progression Shift & Ceiling (min(current + gain, max_level))
9. Dynamic Custom Jury Profile Ingestion & Zero-Downtime Recommendation
10. HR Analytics & Risk Group Identification
"""

from pathlib import Path
import sys
import pytest

# Ensure backend root is on Python sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from data_loader import DataLoader, EmployeeProfile, EventItem, SNAPSHOT_DATE
from main import (
    CompleteActivityRequest,
    CustomProfileUploadRequest,
    RecommendationRequest,
    calculate_multi_factor_recommendations,
    complete_activity,
    get_data_loader,
    get_hr_analytics,
    get_recommendations,
    upload_custom_profiles,
)


@pytest.fixture(scope="module")
def initialized_loader():
    """Provides the shared global instance of DataLoader with official dataset."""
    data_dir = backend_dir.parent / "data"
    loader = get_data_loader(data_dir=data_dir)
    return loader


# ==============================================================================
# TEST 1: Official Employee E0001 (Junior Backend -> Middle Backend)
# ==============================================================================

def test_official_employee_e0001_recommendation(initialized_loader: DataLoader):
    """
    E0001 (Marat Yessenov, Junior Backend Engineer):
    - Target: Middle Backend Engineer
    - Target Critical Skills: SK_PYTHON (3), SK_API_DESIGN (3)
    - Current: SK_PYTHON = 3 (gap 0), SK_API_DESIGN = 2 (gap 1 -> CRITICAL PROMOTION BLOCKER!)
    - History: EV_001, EV_002, EV_003, EV_004, EV_008, EV_011, EV_040 completed
    - Top recommendation MUST be EV_005 (System Design Fundamentals) targeting SK_API_DESIGN
    - Mandatory events (EV_001..EV_004) and completed events (EV_008, EV_011, EV_040) MUST NOT be recommended
    """
    emp = initialized_loader.get_employee("E0001")
    assert emp is not None, "E0001 must exist in official employees dataset"
    assert emp.current_role == "Backend Engineer"
    assert emp.current_grade == "Junior"
    assert emp.target_grade == "Middle"

    recs = calculate_multi_factor_recommendations(emp, initialized_loader, max_recommendations=3)
    assert len(recs) > 0, "Recommendations list must not be empty"

    top_rec = recs[0]
    assert top_rec.event_id == "EV_005", f"Top recommendation for E0001 must be EV_005, got {top_rec.event_id}"
    assert top_rec.target_skill in ["API Design", "SK_API_DESIGN"], f"Target skill must be API Design, got {top_rec.target_skill}"

    # Verify mandatory and completed events are absent
    rec_event_ids = {r.event_id for r in recs}
    mandatory_events = {"EV_001", "EV_002", "EV_003", "EV_004"}
    completed_events = {"EV_008", "EV_011", "EV_040"}
    assert rec_event_ids.isdisjoint(mandatory_events), "Mandatory events must not be recommended"
    assert rec_event_ids.isdisjoint(completed_events), "Completed events must not be recommended"

    # Verify explainable rationale highlights critical blocker (x2.5)
    assert "Критический блокер" in top_rec.rationale or "x2.5" in top_rec.rationale


# ==============================================================================
# TEST 2: Official Employee E0028 (Middle Backend -> Senior Backend)
# ==============================================================================

def test_official_employee_e0028_recommendation(initialized_loader: DataLoader):
    """
    E0028 (Akmaral Ismailova, Middle Backend Engineer):
    - Target: Senior Backend Engineer
    - Target Critical Skills: SK_SYSTEM_DESIGN (needs 4, current 2 -> gap 2, CRITICAL BLOCKER!), SK_API_DESIGN (needs 4, current 4 -> gap 0)
    - History: EV_006 completed (2026-09-08), EV_007 completed (2025-07-29) -> MUST BE EXCLUDED!
    - Also has dropped EV_009 (self_paced) twice, no_show on EV_007 (online).
    - Top recommendation MUST be EV_005 (System Design Fundamentals) targeting SK_SYSTEM_DESIGN.
    """
    emp = initialized_loader.get_employee("E0028")
    assert emp is not None, "E0028 must exist in official employees dataset"
    assert emp.current_role == "Backend Engineer"
    assert emp.current_grade == "Middle"
    assert emp.target_grade == "Senior"

    recs = calculate_multi_factor_recommendations(emp, initialized_loader, max_recommendations=3)
    assert len(recs) > 0, "Recommendations list must not be empty"

    top_rec = recs[0]
    assert top_rec.event_id == "EV_005", f"Top recommendation for E0028 must be EV_005, got {top_rec.event_id}"
    assert top_rec.target_skill in ["System Design", "SK_SYSTEM_DESIGN"]

    rec_event_ids = {r.event_id for r in recs}
    assert "EV_006" not in rec_event_ids, "EV_006 was completed in history and must not be recommended"
    assert "EV_007" not in rec_event_ids, "EV_007 was completed in history and must not be recommended"

    # Verify behavioral penalties were accounted for in rationale
    assert "Штраф истории" in top_rec.rationale or "no_show" in top_rec.rationale or "dropped" in top_rec.rationale


# ==============================================================================
# TEST 3: Strict Mandatory Events Exclusion
# ==============================================================================

def test_strict_mandatory_events_exclusion(initialized_loader: DataLoader):
    """
    Mandatory events (EV_001, EV_002, EV_003, EV_004) are assigned by HR and
    must NEVER appear in upskilling recommendations for any employee.
    """
    sample_ids = ["E0001", "E0002", "E0010", "E0028", "E0050"]
    mandatory_ids = {"EV_001", "EV_002", "EV_003", "EV_004"}

    for eid in sample_ids:
        emp = initialized_loader.get_employee(eid)
        if emp:
            recs = calculate_multi_factor_recommendations(emp, initialized_loader, max_recommendations=5)
            for r in recs:
                assert r.event_id not in mandatory_ids, f"Mandatory event {r.event_id} recommended to {eid}"


# ==============================================================================
# TEST 4: EV_036 (Public Speaking Club) Repeatable Exception
# ==============================================================================

def test_ev036_public_speaking_club_repeatable_exception(initialized_loader: DataLoader):
    """
    Organizer Rule:
    'После статуса completed мероприятие не повторяется. Исключение: EV_036 — регулярный клуб.'
    Verify EV_036 is eligible for recommendation even if marked completed in employee history.
    """
    test_id = "emp_repeatable_club_test"
    raw_profile = {
        "id": test_id,
        "name": "Club Tester",
        "current_role": "Backend Engineer",
        "current_grade": "Junior",
        "target_grade": "Middle",
        "skills": {
            "SK_PYTHON": 3,
            "SK_API_DESIGN": 3,
            "SK_SYSTEM_DESIGN": 2,
            "SK_PUBLIC_SPEAKING": 0,  # Needs 1 for Middle, EV_036 max_level is 4
        },
    }
    initialized_loader.load_custom_profiles([raw_profile])

    # Record EV_036 as already completed in history, and also EV_008 as completed
    initialized_loader.record_activity(test_id, "EV_036", status="completed", score=100.0)
    initialized_loader.record_activity(test_id, "EV_008", status="completed", score=100.0)

    emp = initialized_loader.get_employee(test_id)
    recs = calculate_multi_factor_recommendations(emp, initialized_loader, max_recommendations=25)
    rec_event_ids = [r.event_id for r in recs]

    assert "EV_008" not in rec_event_ids, "Standard completed event EV_008 must be excluded"
    assert "EV_036" in rec_event_ids, "EV_036 (Public Speaking Club) must be allowed to repeat despite completed status"


# ==============================================================================
# TEST 5: Prerequisites Strict Filtering
# ==============================================================================

def test_prerequisites_strict_filtering(initialized_loader: DataLoader):
    """
    EV_010 requires SK_CONTAINERS >= 1.
    If employee has SK_CONTAINERS == 0, EV_010 MUST NOT be recommended.
    """
    test_id = "emp_prereq_test"
    raw_profile = {
        "id": test_id,
        "name": "Prerequisite Tester",
        "current_role": "Backend Engineer",
        "current_grade": "Junior",
        "target_grade": "Middle",
        "skills": {
            "SK_CONTAINERS": 0,  # Below prerequisite (needs 1 for EV_010)
        },
    }
    initialized_loader.load_custom_profiles([raw_profile])
    emp = initialized_loader.get_employee(test_id)

    recs = calculate_multi_factor_recommendations(emp, initialized_loader, max_recommendations=10)
    rec_event_ids = {r.event_id for r in recs}

    assert "EV_010" not in rec_event_ids, "EV_010 must be filtered out due to unmet prerequisites"


# ==============================================================================
# TEST 6: Upper Ceiling Cap (max_level) Filtering
# ==============================================================================

def test_ceiling_cap_filtering(initialized_loader: DataLoader):
    """
    EV_005 develops SK_SYSTEM_DESIGN (max_level 3) and SK_API_DESIGN (max_level 3).
    If employee already has both skills at level >= 3, EV_005 yields 0 gain and MUST be filtered out.
    """
    test_id = "emp_ceiling_test"
    raw_profile = {
        "id": test_id,
        "name": "Ceiling Tester",
        "current_role": "Backend Engineer",
        "current_grade": "Middle",
        "target_grade": "Senior",
        "skills": {
            "SK_SYSTEM_DESIGN": 3,  # Already at max_level for EV_005
            "SK_API_DESIGN": 3,     # Already at max_level for EV_005
        },
    }
    initialized_loader.load_custom_profiles([raw_profile])
    emp = initialized_loader.get_employee(test_id)

    recs = calculate_multi_factor_recommendations(emp, initialized_loader, max_recommendations=10)
    rec_event_ids = {r.event_id for r in recs}

    assert "EV_005" not in rec_event_ids, "EV_005 must be filtered out when current skill levels reach max_level"


# ==============================================================================
# TEST 7: The Jury Corner-Case Trap (Failure of Naive Single-Factor Rule)
# ==============================================================================

def test_jury_corner_case_naive_rule_trap(initialized_loader: DataLoader):
    """
    JURY EDGE CASE CRITERION:
    Naive rule: Pick the skill with minimum level (Public Speaking = 1).
    Why it fails:
    - Target grade is Senior Backend Engineer.
    - System Design is at level 2 (requires 4) -> HARD PROMOTION BLOCKER (Critical Skill)!
    - Public Speaking is at level 1, but is NOT a critical requirement for Senior Backend promotion.
    - Candidate also has dropped/no-show on soft-skill offline events in history.

    EXPECTED RESULT:
    Multi-factor engine MUST recommend System Design (EV_005), NOT Public Speaking (EV_036)!
    """
    candidate_id = "jury_trap_middle_candidate_001"
    raw_profile = {
        "id": candidate_id,
        "name": "Темирлан Бериков (Jury Corner Case)",
        "department": "Core Banking",
        "current_role": "Backend Engineer",
        "current_grade": "Middle",
        "target_grade": "Senior",
        "skills": {
            "SK_PYTHON": 4,
            "SK_SQL": 4,
            "SK_API_DESIGN": 4,
            "SK_SYSTEM_DESIGN": 2,      # Level 2 -> Needs 4 for Senior (Gap: 2, CRITICAL BLOCKER)
            "SK_PUBLIC_SPEAKING": 1,    # Level 1 (MINIMAL SKILL, but NOT critical)
        },
        "preferences": {
            "preferred_formats": ["online"],
        },
    }

    loaded_profiles, errors = initialized_loader.load_custom_profiles([raw_profile])
    assert len(loaded_profiles) == 1
    assert not errors

    # Record dropped/no-show offline events
    initialized_loader.record_activity(candidate_id, "EV_036", status="dropped", score=0.0, feedback="Бросил клуб")
    initialized_loader.record_activity(candidate_id, "EV_023", status="no_show", score=0.0, feedback="Не явился")

    emp = initialized_loader.get_employee(candidate_id)
    recs = calculate_multi_factor_recommendations(emp, initialized_loader, max_recommendations=3)

    assert len(recs) > 0, "Recommendations list must not be empty"
    top_rec = recs[0]

    assert top_rec.target_skill in ["System Design", "SK_SYSTEM_DESIGN"], (
        f"Multi-factor model must recommend System Design to unblock Senior grade, "
        f"got '{top_rec.target_skill}' instead (naive single-factor trap!)."
    )
    assert top_rec.event_id in ["EV_005", "EV_006", "EV_007"], (
        f"Expected System Design unblocking event (EV_005/EV_006/EV_007), got {top_rec.event_id}"
    )
    assert recs[0].target_skill != "Public Speaking"
    assert "Критический блокер" in top_rec.rationale or "разрыв" in top_rec.rationale


# ==============================================================================
# TEST 8: Skill Progression Shift & Upper Ceiling Cap
# ==============================================================================

def test_skill_progress_shift_and_ceiling(initialized_loader: DataLoader):
    """
    CRITERION:
    When an employee completes an activity:
    - Skill increases by event gain: new_level = min(current + gain, max_level)
    - State updates in memory
    - Level does not exceed event's max_level (3 for EV_005)
    """
    test_emp_id = "emp_progression_test"
    raw_profile = {
        "id": test_emp_id,
        "name": "Айсулу Нурланова",
        "current_role": "Backend Engineer",
        "current_grade": "Middle",
        "target_grade": "Senior",
        "skills": {
            "SK_SYSTEM_DESIGN": 1,
            "SK_API_DESIGN": 2,
        },
    }
    initialized_loader.load_custom_profiles([raw_profile])

    # 1. Complete event EV_005 (gain: 1, max_level: 3)
    req = CompleteActivityRequest(employee_id=test_emp_id, event_id="EV_005")
    resp = complete_activity(req)

    assert resp.status == "success"
    updated_emp = resp.employee

    assert updated_emp.skills["SK_SYSTEM_DESIGN"] == 2
    assert updated_emp.skills["SK_API_DESIGN"] == 3

    # 2. Retry the same completion: neither skills nor points may be farmed twice.
    resp2 = complete_activity(req)
    assert resp2.employee.skills["SK_API_DESIGN"] == 3
    assert resp2.employee.skills["SK_SYSTEM_DESIGN"] == 2
    assert resp2.points_awarded == 0


# ==============================================================================
# TEST 9: Dynamic Custom Profile Ingestion & Zero-Downtime Recommendation
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
                "department": "Data Analytics",
                "current_role": "Data Analyst",
                "current_grade": "Junior",
                "target_grade": "Middle",
                "skills": {
                    "SK_PYTHON": 3,
                    "SK_SQL": 2,          # Critical for Middle Data Analyst (needs 3, gap 1)
                    "SK_STATISTICS": 1,   # Critical for Middle Data Analyst (needs 2, gap 1)
                },
                "preferences": {
                    "preferred_formats": ["online"],
                },
            }
        ]
    )

    upload_res = upload_custom_profiles(upload_payload)
    assert upload_res.status == "success"
    assert custom_jury_id in upload_res.profile_ids

    rec_req = RecommendationRequest(employee_id=custom_jury_id)
    rec_res = get_recommendations(rec_req)

    assert rec_res.employee_id == custom_jury_id
    assert len(rec_res.recommendations) > 0

    top_skill = rec_res.recommendations[0].target_skill
    assert top_skill in ["Statistics", "SQL", "SK_STATISTICS", "SK_SQL"]


# ==============================================================================
# TEST 10: HR Analytics (Skills Deficit & Engagement Risk Group)
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

    if analytics.top_deficit_skills:
        first = analytics.top_deficit_skills[0]
        assert "skill" in first
        assert "total_gap" in first
        assert first["total_gap"] >= 0
