"""Persistent Quest Points wallet, reward catalog, and approval ledger."""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REWARDS: list[dict[str, Any]] = [
    {"id": "conference", "title": "Conference participation", "category": "Professional Growth", "description": "Support for an external conference or professional intensive aligned with your career path.", "cost": 1500, "availability": "12 spots left", "icon": "↗", "featured": True},
    {"id": "library", "title": "Professional course subscription", "category": "Professional Growth", "description": "A curated annual subscription to professional libraries and learning platforms.", "cost": 1700, "availability": "Available", "icon": "◎"},
    {"id": "hoodie", "title": "Halyk branded hoodie", "category": "Halyk Brand", "description": "A comfortable branded hoodie for your everyday work and travel.", "cost": 500, "availability": "24 available", "icon": "◒"},
    {"id": "coffee", "title": "Mentoring coffee", "category": "Work-Life Balance", "description": "A private 1-on-1 conversation with a senior expert or leader from Halyk.", "cost": 200, "availability": "Available", "icon": "☕"},
    {"id": "dayoff", "title": "Learning day-off", "category": "Work-Life Balance", "description": "A floating day for focused voluntary learning, subject to HR approval.", "cost": 2200, "availability": "Approval required", "icon": "○"},
    {"id": "shopper", "title": "Halyk branded shopper", "category": "Halyk Brand", "description": "A practical reusable shopper with a subtle Halyk identity.", "cost": 250, "availability": "Available", "icon": "□"},
]
REWARD_BY_ID = {item["id"]: item for item in REWARDS}


class RewardsStore:
    def __init__(self, db_path: str | None = None):
        configured_path = db_path or os.getenv("REWARDS_DB_PATH")
        self.db_path = Path(configured_path) if configured_path else Path(__file__).resolve().parent / "state" / "rewards.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS point_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(employee_id, kind, reference)
                );
                CREATE TABLE IF NOT EXISTS reward_requests (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL,
                    reward_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    cost INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('Pending', 'Approved', 'Rejected')),
                    requested_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_reward_requests_employee ON reward_requests(employee_id, requested_at DESC);
                CREATE TABLE IF NOT EXISTS purchase_keys (
                    employee_id TEXT NOT NULL, request_key TEXT NOT NULL,
                    request_id TEXT NOT NULL REFERENCES reward_requests(id),
                    PRIMARY KEY(employee_id, request_key)
                );
                CREATE TABLE IF NOT EXISTS profile_state (
                    employee_id TEXT PRIMARY KEY, profile_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS completed_activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT NOT NULL,
                    event_id TEXT NOT NULL, event_date TEXT NOT NULL,
                    request_key TEXT, UNIQUE(employee_id, request_key)
                );
                CREATE TABLE IF NOT EXISTS issued_rewards (
                    request_id TEXT PRIMARY KEY REFERENCES reward_requests(id), issued_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('employee','hr')),
                    employee_id TEXT, failures INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES users(username),
                    expires_at REAL NOT NULL
                );
            """)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def award_activity(self, employee_id: str, event_id: str, points: int = 150) -> tuple[int, int]:
        """Award once per employee/event, even if the completion endpoint is retried."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "INSERT OR IGNORE INTO point_transactions(employee_id,amount,kind,reference,description,created_at) VALUES(?,?,?,?,?,?)",
                (employee_id, points, "earned", event_id, f"Completed activity {event_id}", self._now()),
            )
            awarded = points if cur.rowcount == 1 else 0
            balance = conn.execute("SELECT COALESCE(SUM(amount),0) FROM point_transactions WHERE employee_id=?", (employee_id,)).fetchone()[0]
            conn.commit()
            return awarded, int(balance)

    def wallet(self, employee_id: str) -> dict[str, int | str]:
        with closing(self._connect()) as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(amount),0) balance,
                       COALESCE(SUM(CASE WHEN kind='earned' THEN amount ELSE 0 END),0) earned,
                       COALESCE(-SUM(CASE WHEN kind IN ('redeemed','refund') THEN amount ELSE 0 END),0) spent
                FROM point_transactions WHERE employee_id=?
            """, (employee_id,)).fetchone()
        return {"employee_id": employee_id, "balance": int(row["balance"]), "total_earned": int(row["earned"]), "total_spent": int(row["spent"])}

    def requests(self, employee_id: str | None = None) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            if employee_id:
                rows = conn.execute("SELECT r.*, i.issued_at FROM reward_requests r LEFT JOIN issued_rewards i ON r.id=i.request_id WHERE employee_id=? ORDER BY requested_at DESC, r.rowid DESC", (employee_id,)).fetchall()
            else:
                rows = conn.execute("SELECT r.*, i.issued_at FROM reward_requests r LEFT JOIN issued_rewards i ON r.id=i.request_id ORDER BY requested_at DESC, r.rowid DESC").fetchall()
        return [self._request_row(r) for r in rows]

    @staticmethod
    def _request_row(r) -> dict[str, Any]:
        return {"id": r["id"], "employee_id": r["employee_id"], "rewardId": r["reward_id"], "title": r["title"], "category": r["category"], "cost": r["cost"], "status": "Redeemed" if r["issued_at"] else r["status"], "requestedAt": r["requested_at"], "decidedAt": r["decided_at"]}

    def redeem(self, employee_id: str, reward_id: str, request_key: str | None = None) -> dict[str, Any]:
        reward = REWARD_BY_ID.get(reward_id)
        if not reward:
            raise KeyError("Reward not found")
        request_id = str(uuid.uuid4())
        now = self._now()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            balance = int(conn.execute("SELECT COALESCE(SUM(amount),0) FROM point_transactions WHERE employee_id=?", (employee_id,)).fetchone()[0])
            if request_key:
                existing = conn.execute("SELECT r.*, i.issued_at FROM purchase_keys k JOIN reward_requests r ON r.id=k.request_id LEFT JOIN issued_rewards i ON i.request_id=r.id WHERE k.employee_id=? AND k.request_key=?", (employee_id, request_key)).fetchone()
                if existing:
                    if existing["reward_id"] != reward_id:
                        raise ValueError("Idempotency key was used for another reward")
                    conn.commit()
                    return {**self._request_row(existing), "balance": balance}
            else:
                # Compatibility with the supplied UI, which does not send a request key yet.
                existing = conn.execute("SELECT r.*, NULL issued_at FROM reward_requests r WHERE employee_id=? AND reward_id=? AND status='Pending'", (employee_id, reward_id)).fetchone()
                if existing:
                    conn.commit()
                    return {**self._request_row(existing), "balance": balance}
            stock = {"conference": 12, "hoodie": 24}.get(reward_id)
            if stock is not None:
                reserved = conn.execute("SELECT COUNT(*) FROM reward_requests WHERE reward_id=? AND status!='Rejected'", (reward_id,)).fetchone()[0]
                if reserved >= stock:
                    raise ValueError("Reward is out of stock")
            if balance < reward["cost"]:
                conn.rollback()
                raise ValueError("Not enough Quest Points")
            conn.execute("INSERT INTO point_transactions(employee_id,amount,kind,reference,description,created_at) VALUES(?,?,?,?,?,?)", (employee_id, -reward["cost"], "redeemed", request_id, f"Reward request: {reward['title']}", now))
            conn.execute("INSERT INTO reward_requests(id,employee_id,reward_id,title,category,cost,status,requested_at) VALUES(?,?,?,?,?,?,?,?)", (request_id, employee_id, reward_id, reward["title"], reward["category"], reward["cost"], "Pending", now))
            if request_key:
                conn.execute("INSERT INTO purchase_keys VALUES(?,?,?)", (employee_id, request_key, request_id))
            balance -= reward["cost"]
            conn.commit()
        return {"id": request_id, "employee_id": employee_id, "rewardId": reward_id, "title": reward["title"], "category": reward["category"], "cost": reward["cost"], "status": "Pending", "requestedAt": now, "balance": balance}

    def decide(self, request_id: str, decision: str) -> dict[str, Any]:
        if decision not in {"Approved", "Rejected"}:
            raise ValueError("Decision must be Approved or Rejected")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM reward_requests WHERE id=?", (request_id,)).fetchone()
            if not row:
                conn.rollback()
                raise KeyError("Reward request not found")
            if row["status"] != "Pending":
                conn.rollback()
                raise ValueError("Reward request has already been decided")
            now = self._now()
            conn.execute("UPDATE reward_requests SET status=?, decided_at=? WHERE id=?", (decision, now, request_id))
            if decision == "Rejected":
                conn.execute("INSERT OR IGNORE INTO point_transactions(employee_id,amount,kind,reference,description,created_at) VALUES(?,?,?,?,?,?)", (row["employee_id"], row["cost"], "refund", request_id, f"Refund for rejected reward {row['title']}", now))
            conn.commit()
        return next(item for item in self.requests(row["employee_id"]) if item["id"] == request_id)

    def analytics(self) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            totals = conn.execute("""
                SELECT COALESCE(SUM(CASE WHEN kind='earned' THEN amount ELSE 0 END),0) earned,
                       COALESCE(-SUM(CASE WHEN kind IN ('redeemed','refund') THEN amount ELSE 0 END),0) redeemed,
                       COUNT(DISTINCT CASE WHEN kind='earned' THEN employee_id END) active
                FROM point_transactions
            """).fetchone()
            rows = conn.execute("SELECT category, COUNT(*) requests, SUM(CASE WHEN status='Approved' THEN 1 ELSE 0 END) approved, SUM(CASE WHEN status IN ('Pending','Approved') THEN cost ELSE 0 END) spent FROM reward_requests GROUP BY category ORDER BY requests DESC").fetchall()
            popular = conn.execute("SELECT title,category,COUNT(*) requests,SUM(CASE WHEN status='Approved' THEN 1 ELSE 0 END) approved,SUM(CASE WHEN status IN ('Pending','Approved') THEN cost ELSE 0 END) spent FROM reward_requests GROUP BY reward_id ORDER BY requests DESC LIMIT 5").fetchall()
            pending = int(conn.execute("SELECT COUNT(*) FROM reward_requests WHERE status='Pending'").fetchone()[0])
            stage_counts = {"Earned QP": int(totals["active"]), "Requested": int(conn.execute("SELECT COUNT(DISTINCT employee_id) FROM reward_requests").fetchone()[0]), "Approved": int(conn.execute("SELECT COUNT(DISTINCT employee_id) FROM reward_requests WHERE status='Approved'").fetchone()[0]), "Redeemed": int(conn.execute("SELECT COUNT(DISTINCT r.employee_id) FROM issued_rewards i JOIN reward_requests r ON r.id=i.request_id").fetchone()[0])}
        total_requests = sum(int(row["requests"]) for row in rows)
        category_share = {category: 0 for category in ("Halyk Brand", "Professional Growth", "Work-Life Balance")}
        for row in rows:
            category_share[row["category"]] = round(100 * int(row["requests"]) / total_requests) if total_requests else 0
        most_popular = rows[0]["category"] if rows else "Professional Growth"
        return {
            "totalQpAwarded": int(totals["earned"]), "totalQpRedeemed": int(totals["redeemed"]), "activeUsers": int(totals["active"]), "popularCategory": most_popular,
            "pendingApprovals": pending, "categoryShare": category_share,
            "popularRewards": [{"title": r["title"], "category": r["category"], "requests": int(r["requests"]), "approved": int(r["approved"]), "spent": int(r["spent"])} for r in popular],
            "journey": [{"label": label, "count": count} for label, count in stage_counts.items()],
        }

    def catalog(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            reserved = dict(conn.execute("SELECT reward_id,COUNT(*) FROM reward_requests WHERE status!='Rejected' GROUP BY reward_id").fetchall())
        result = []
        for reward in REWARDS:
            item = dict(reward)
            stock = {"conference": 12, "hoodie": 24}.get(item["id"])
            if stock is not None:
                item["stock_remaining"] = max(0, stock - reserved.get(item["id"], 0))
                item["availability"] = f"{item['stock_remaining']} available"
            result.append(item)
        return result

    def fulfill(self, request_id: str) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM reward_requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise KeyError("Reward request not found")
            if row["status"] != "Approved":
                raise ValueError("Only an approved request can be fulfilled")
            conn.execute("INSERT OR IGNORE INTO issued_rewards VALUES(?,?)", (request_id, self._now()))
            conn.commit()
        return next(r for r in self.requests(row["employee_id"]) if r["id"] == request_id)

    def transactions(self, employee_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            return [dict(row) for row in conn.execute("SELECT id,amount,kind,reference,description,created_at FROM point_transactions WHERE employee_id=? ORDER BY id DESC LIMIT 100", (employee_id,))]

    def save_profiles(self, profiles) -> None:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for profile in profiles:
                conn.execute("INSERT OR REPLACE INTO profile_state VALUES(?,?)", (profile.employee_id, profile.model_dump_json()))
            conn.commit()

    def save_completion(self, profile, event_id: str, event_date: str, award: bool, request_key: str | None) -> tuple[int, int, int]:
        """Commit skill state, history and points together before changing the in-memory view."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            operation = conn.execute("INSERT INTO completed_activities(employee_id,event_id,event_date,request_key) VALUES(?,?,?,?)", (profile.employee_id, event_id, event_date, request_key))
            conn.execute("INSERT OR REPLACE INTO profile_state VALUES(?,?)", (profile.employee_id, profile.model_dump_json()))
            awarded = 0
            if award:
                cur = conn.execute("INSERT OR IGNORE INTO point_transactions(employee_id,amount,kind,reference,description,created_at) VALUES(?,?,?,?,?,?)", (profile.employee_id, 150, "earned", event_id, f"Completed activity {event_id}", self._now()))
                awarded = 150 if cur.rowcount else 0
            balance = int(conn.execute("SELECT COALESCE(SUM(amount),0) FROM point_transactions WHERE employee_id=?", (profile.employee_id,)).fetchone()[0])
            conn.commit()
        return awarded, balance, operation.lastrowid

    def completion_exists(self, employee_id: str, event_id: str, request_key: str | None = None) -> bool:
        with closing(self._connect()) as conn:
            if request_key:
                row = conn.execute("SELECT event_id FROM completed_activities WHERE employee_id=? AND request_key=?", (employee_id, request_key)).fetchone()
                if row and row["event_id"] != event_id:
                    raise ValueError("Idempotency key was used for another activity")
                return row is not None
            return conn.execute("SELECT 1 FROM completed_activities WHERE employee_id=? AND event_id=? LIMIT 1", (employee_id, event_id)).fetchone() is not None

    def restore(self, loader) -> None:
        from data_loader import EmployeeProfile
        with closing(self._connect()) as conn, loader.lock:
            for row in conn.execute("SELECT profile_json FROM profile_state"):
                profile = EmployeeProfile.model_validate_json(row["profile_json"])
                loader._employees[profile.employee_id] = profile
                if profile.is_custom:
                    loader._custom_profiles[profile.employee_id] = profile
            for row in conn.execute("SELECT * FROM completed_activities ORDER BY id"):
                record_id = f"DB_{row['id']}"
                history = loader._activity_history
                if not history.empty and "record_id" in history and (history["record_id"] == record_id).any():
                    continue
                loader.record_activity(row["employee_id"], row["event_id"], event_date=row["event_date"], record_id=record_id)
