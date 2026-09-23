from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main
from rewards import RewardsStore


@pytest.fixture
def store(tmp_path):
    return RewardsStore(str(tmp_path / "quest-points.sqlite3"))


def test_activity_points_are_awarded_once_per_employee_and_event(store):
    assert store.award_activity("E0001", "EV_005") == (150, 150)
    assert store.award_activity("E0001", "EV_005") == (0, 150)
    assert store.award_activity("E0001", "EV_006") == (150, 300)


def test_redemption_requires_enough_points(store):
    with pytest.raises(ValueError, match="Not enough"):
        store.redeem("E0001", "coffee")
    assert store.wallet("E0001")["balance"] == 0
    assert store.requests("E0001") == []


def test_rejected_reward_refunds_points_exactly_once(store):
    store.award_activity("E0001", "EV_005", points=300)
    request = store.redeem("E0001", "coffee")
    assert request["balance"] == 100

    assert store.decide(request["id"], "Rejected")["status"] == "Rejected"
    assert store.wallet("E0001")["balance"] == 300
    assert store.wallet("E0001")["total_spent"] == 0
    with pytest.raises(ValueError, match="already been decided"):
        store.decide(request["id"], "Rejected")
    assert store.wallet("E0001")["balance"] == 300


def test_approved_reward_stays_deducted_and_appears_in_analytics(store):
    store.award_activity("E0001", "EV_005", points=500)
    request = store.redeem("E0001", "hoodie")
    assert store.decide(request["id"], "Approved")["status"] == "Approved"
    assert store.wallet("E0001")["balance"] == 0

    report = store.analytics()
    assert report["totalQpAwarded"] == 500
    assert report["totalQpRedeemed"] == 500
    assert report["pendingApprovals"] == 0
    assert report["popularRewards"][0]["title"] == "Halyk branded hoodie"


def test_api_wallet_and_redeem_routes_use_server_balance(tmp_path, monkeypatch):
    ledger = RewardsStore(str(tmp_path / "api-wallet.sqlite3"))
    ledger.award_activity("E0001", "EV_005", points=500)
    monkeypatch.setattr(main, "_rewards_store_instance", ledger)

    with TestClient(main.app) as client:
        wallet = client.get("/api/employees/E0001/points")
        assert wallet.status_code == 200
        assert wallet.json()["balance"] == 500

        redemption = client.post("/api/rewards/coffee/redeem", json={"employee_id": "E0001"})
        assert redemption.status_code == 201
        assert redemption.json()["balance"] == 300

        refreshed = client.get("/api/employees/E0001/points")
        assert refreshed.json()["balance"] == 300
