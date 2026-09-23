from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from auth import AuthService
from data_loader import DataLoader


@pytest.fixture
def client(monkeypatch):
    loader = DataLoader(Path(__file__).resolve().parents[2] / "data")
    loader.load_all()
    monkeypatch.setattr(main, "get_data_loader", lambda: loader)
    with TestClient(main.app) as client:
        yield client


def add_profile(client, employee_id="TEST_FLOW", level=1):
    response = client.post("/api/profiles/upload", json={"profiles": [{
        "employee_id": employee_id, "full_name": "Demo Test", "role": "Backend Engineer", "grade": "Middle",
        "skills": {"SK_SYSTEM_DESIGN": level, "SK_API_DESIGN": 2, "SK_PUBLIC_SPEAKING": 0},
    }]})
    assert response.status_code == 201
    return employee_id


def test_progress_and_wallet_survive_restart_without_duplicate_history(client, monkeypatch):
    employee = add_profile(client)
    response = client.post("/api/activities/EV_005/complete", json={"employee_id": employee})
    assert response.status_code == 200
    assert response.json()["points_awarded"] == 150
    assert response.json()["skill_updates"][0]["skill_id"].startswith("SK_")
    repeat = client.post("/api/activities/EV_005/complete", json={"employee_id": employee})
    assert repeat.json()["points_awarded"] == 0
    assert len(main.get_data_loader().get_employee_history(employee)) == 1
    restored = DataLoader(Path(__file__).resolve().parents[2] / "data")
    restored.load_all()
    main.get_rewards_store().restore(restored)
    main.get_rewards_store().restore(restored)
    assert restored.get_employee(employee).skills["SK_SYSTEM_DESIGN"] == 2
    assert len(restored.get_employee_history(employee)) == 1
    monkeypatch.setattr(main, "get_data_loader", lambda: restored)
    assert client.get(f"/api/employees/{employee}/points").json()["balance"] == 150
    assert client.post("/api/activities/EV_005/complete", json={"employee_id": employee}).json()["points_awarded"] == 0


def test_intro_course_does_not_lower_existing_expert_skills(client):
    employee = add_profile(client, level=5)
    client.post("/api/activities/EV_005/complete", json={"employee_id": employee})
    assert main.get_data_loader().get_employee(employee).skills["SK_SYSTEM_DESIGN"] == 5


def test_repeatable_club_supports_distinct_sessions_but_not_duplicate_retries(client):
    employee = add_profile(client)
    path = "/api/activities/EV_036/complete"
    first = client.post(path, json={"employee_id": employee}, headers={"Idempotency-Key": "session-1"})
    retry = client.post(path, json={"employee_id": employee}, headers={"Idempotency-Key": "session-1"})
    second = client.post(path, json={"employee_id": employee}, headers={"Idempotency-Key": "session-2"})
    assert first.json()["points_awarded"] == 150
    assert retry.json()["points_awarded"] == second.json()["points_awarded"] == 0
    assert main.get_data_loader().get_employee(employee).skills["SK_PUBLIC_SPEAKING"] == 2


def test_purchase_retry_refund_and_fulfillment(client):
    store = main.get_rewards_store()
    store.award_activity("E0001", "TEST_CREDIT", 500)
    path = "/api/rewards/coffee/redeem"
    first = client.post(path, json={"employee_id": "E0001"}, headers={"Idempotency-Key": "purchase-1"})
    retry = client.post(path, json={"employee_id": "E0001"}, headers={"Idempotency-Key": "purchase-1"})
    assert first.json()["id"] == retry.json()["id"]
    request_id = first.json()["id"]
    assert client.post(f"/api/hr/rewards/requests/{request_id}/decision", json={"decision": "Rejected"}).status_code == 200
    assert store.wallet("E0001") == {"employee_id": "E0001", "balance": 500, "total_earned": 500, "total_spent": 0}
    assert store.analytics()["totalQpAwarded"] == 500
    second = client.post(path, json={"employee_id": "E0001"}, headers={"Idempotency-Key": "purchase-2"}).json()
    assert client.post(f"/api/hr/rewards/requests/{second['id']}/fulfill").status_code == 409
    client.post(f"/api/hr/rewards/requests/{second['id']}/decision", json={"decision": "Approved"})
    issued = client.post(f"/api/hr/rewards/requests/{second['id']}/fulfill")
    assert issued.json()["status"] == "Redeemed"
    assert client.post(f"/api/hr/rewards/requests/{second['id']}/fulfill").status_code == 200
    assert len(client.get("/api/employees/E0001/points/transactions").json()) == 4


def test_parallel_purchases_cannot_overdraw_wallet():
    store = main.get_rewards_store()
    store.award_activity("E0001", "TEST_CREDIT", 300)
    def purchase(key):
        try:
            return store.redeem("E0001", "coffee", key)
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(purchase, ["A", "B"]))
    assert len([r for r in results if r]) == 1
    assert store.wallet("E0001")["balance"] == 100


def test_finite_stock_is_reserved_and_released_on_rejection():
    store = main.get_rewards_store()
    for i in range(25):
        store.award_activity(f"EMP_{i}", "TEST_CREDIT", 500)
    requests = [store.redeem(f"EMP_{i}", "hoodie") for i in range(24)]
    with pytest.raises(ValueError, match="out of stock"):
        store.redeem("EMP_24", "hoodie")
    store.decide(requests[0]["id"], "Rejected")
    assert store.redeem("EMP_24", "hoodie")["status"] == "Pending"


def test_upload_wrapper_invalid_json_and_missing_employee(client):
    uploaded = client.post("/api/profiles/upload-file", files={"file": ("profiles.json", '{"profiles":[{"id":"JURY_WRAP","name":"Jury","role":"Backend Engineer","grade":"Middle"}]}', "application/json")})
    assert uploaded.status_code == 201
    assert uploaded.json()["profile_ids"] == ["JURY_WRAP"]
    assert client.post("/api/profiles/upload-file", files={"file": ("bad.json", "not json")}).status_code == 400
    assert client.get("/api/employees/MISSING/points").status_code == 404


def test_authenticated_employee_cannot_access_other_users_or_hr(client, monkeypatch):
    auth = AuthService(main.get_rewards_store())
    auth.create_user("employee@example.test", "Employee-password-123", "employee", "E0001")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    assert client.get("/api/employees/E0001/points").status_code == 401
    assert client.get("/api/auth/me").json()["authenticated"] is False
    signed_in = client.post("/api/auth/login", json={"username": "employee@example.test", "password": "Employee-password-123"})
    assert signed_in.status_code == 200
    assert "HttpOnly" in signed_in.headers["set-cookie"]
    token = signed_in.json()["access_token"]
    assert len(client.get("/api/employees").json()) == 1
    assert client.get("/api/employees/E0001/points").status_code == 200
    assert client.get("/api/employees/E0028/points").status_code == 403
    assert client.get("/api/hr/rewards/requests").status_code == 403
    assert client.post("/api/recommendations", json={"employee_id": "E0028"}).status_code == 403
    assert client.post("/api/recommendations", json={"employee_id": "E0001"}).status_code == 200
    assert client.post("/api/rewards/coffee/redeem", json={"employee_id": "E0001"}, headers={"Origin": "https://untrusted.test"}).status_code == 403
    client.post("/api/auth/logout")
    assert client.get("/api/employees/E0001/points", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_hr_access_and_expiring_sessions(client, monkeypatch):
    store = main.get_rewards_store()
    AuthService(store).create_user("hr@example.test", "HR-password-12345", "hr")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    assert client.post("/api/auth/login", json={"username": "hr@example.test", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "hr@example.test", "password": "HR-password-12345"}).status_code == 200
    assert client.get("/api/hr/rewards/requests").status_code == 200
    assert len(client.get("/api/employees").json()) == 200
    with closing(store._connect()) as conn:
        conn.execute("UPDATE sessions SET expires_at=0")
    assert client.get("/api/hr/rewards/requests").status_code == 401
