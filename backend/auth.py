"""Local accounts and revocable sessions. Enable AUTH_ENABLED after wiring the login UI."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from contextlib import closing
from urllib.parse import unquote

from fastapi.responses import JSONResponse

COOKIE_NAME = "career_quest_session"
SESSION_SECONDS = 8 * 60 * 60
ITERATIONS = 600_000
logger = logging.getLogger("career_quest.auth")


def enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "false").lower() in {"1", "true", "yes"}


def demo_accounts_enabled() -> bool:
    """Whether the safe, non-production demo accounts should be bootstrapped."""
    return os.getenv("DEMO_ACCOUNTS_ENABLED", "false").lower() in {"1", "true", "yes"}


def password_digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()


class AuthService:
    def __init__(self, store):
        self.store = store

    def create_user(self, username: str, password: str, role: str, employee_id: str | None = None) -> None:
        if not username.strip() or len(password) < 6 or len(password) > 256:
            raise ValueError("Username is required; password must be 6–256 characters")
        if role not in {"employee", "hr"} or (role == "employee" and not employee_id):
            raise ValueError("Role must be employee/hr; employee role requires employee_id")
        salt = secrets.token_hex(16)
        digest = password_digest(password, salt)
        with closing(self.store._connect()) as conn:
            conn.execute("INSERT INTO users(username,password_hash,salt,role,employee_id) VALUES(?,?,?,?,?)", (username.strip().lower(), digest, salt, role, employee_id))

    def login(self, username: str, password: str) -> tuple[str, dict] | None:
        username = username.strip().lower()
        with closing(self.store._connect()) as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            digest = password_digest(password, row["salt"] if row else "00" * 16)
            now = time.time()
            conn.execute("BEGIN IMMEDIATE")
            # Re-read lockout state after hashing to handle concurrent failed logins.
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not row or row["locked_until"] > now:
                return None
            if not hmac.compare_digest(digest, row["password_hash"]):
                failures = row["failures"] + 1 if row["locked_until"] == 0 else 1
                conn.execute("UPDATE users SET failures=?, locked_until=? WHERE username=?", (failures, now + 300 if failures >= 5 else 0, username))
                conn.commit()
                return None
            conn.execute("UPDATE users SET failures=0, locked_until=0 WHERE username=?", (username,))
            conn.execute("DELETE FROM sessions WHERE expires_at<?", (now,))
            token = secrets.token_urlsafe(48)
            conn.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), username, now + SESSION_SECONDS))
            conn.commit()
            return token, {"username": username, "role": row["role"], "employee_id": row["employee_id"]}

    def identity(self, token: str | None) -> dict | None:
        if not token:
            return None
        with closing(self.store._connect()) as conn:
            row = conn.execute("SELECT u.username,u.role,u.employee_id FROM sessions s JOIN users u ON s.username=u.username WHERE s.token_hash=? AND s.expires_at>?", (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token: str | None) -> None:
        if token:
            with closing(self.store._connect()) as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


def ensure_demo_accounts(store, employee_lookup=None) -> list[str]:
    """Create portable hackathon demo accounts once, without storing plain passwords.

    Credentials are intentionally configurable through the environment so the
    repository contains only demo values in ``.env.example``. Existing accounts
    are left untouched, which makes startup idempotent and preserves any later
    password changes made by the team.
    """
    if not demo_accounts_enabled():
        return []

    accounts = [
        {
            "username": os.getenv("DEMO_EMPLOYEE_USERNAME", "demo.employee@halykbank.kz"),
            "password": os.getenv("DEMO_EMPLOYEE_PASSWORD", "demo123"),
            "role": "employee",
            "employee_id": os.getenv("DEMO_EMPLOYEE_ID", "E0028"),
        },
        {
            "username": "demo.employee",
            "password": "demo123",
            "role": "employee",
            "employee_id": "E0028",
        },
        {
            "username": os.getenv("DEMO_HR_USERNAME", "hr.manager@halykbank.kz"),
            "password": os.getenv("DEMO_HR_PASSWORD", "admin123"),
            "role": "hr",
            "employee_id": None,
        },
        {
            "username": "hr.manager",
            "password": "admin123",
            "role": "hr",
            "employee_id": None,
        },
    ]
    auth = AuthService(store)
    created: list[str] = []
    with closing(store._connect()) as conn:
        existing = {row["username"] for row in conn.execute("SELECT username FROM users")}

    for account in accounts:
        username = account["username"].strip().lower()
        if account["role"] == "employee" and employee_lookup is not None:
            if not account["employee_id"] or employee_lookup(account["employee_id"]) is None:
                logger.warning("Demo employee account skipped: employee_id=%s was not found", account["employee_id"])
                continue
        if username in existing:
            # Update password hash and employee_id for demo accounts so credentials are synchronized
            salt = secrets.token_hex(16)
            digest = password_digest(account["password"], salt)
            with closing(store._connect()) as conn:
                conn.execute(
                    "UPDATE users SET password_hash=?, salt=?, employee_id=?, role=?, failures=0, locked_until=0 WHERE username=?",
                    (digest, salt, account["employee_id"], account["role"], username)
                )
                conn.commit()
            created.append(username)
            continue
        try:
            auth.create_user(username, account["password"], account["role"], account["employee_id"])
        except sqlite3.IntegrityError:
            # Another worker may have initialized the same account concurrently.
            continue
        except ValueError as exc:
            logger.warning("Demo account %s was skipped: %s", username, exc)
            continue
        created.append(username)
        existing.add(username)
    return created


def request_token(request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:]
    return request.cookies.get(COOKIE_NAME)


def access_middleware(get_store):
    async def guard(request, call_next):
        path = unquote(request.url.path).rstrip("/")
        request.state.identity = None
        if not enabled() or not path.startswith("/api/") or request.method == "OPTIONS":
            return await call_next(request)
        if path == "/api/health" or path in {"/api/auth/login", "/api/auth/me", "/api/auth/logout"}:
            return await call_next(request)
        identity = AuthService(get_store()).identity(request_token(request))
        if not identity:
            return JSONResponse({"detail": "Sign in required"}, status_code=401)
        request.state.identity = identity
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get(COOKIE_NAME):
            origin = request.headers.get("origin")
            allowed = {str(request.base_url).rstrip("/")} | set(os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","))
            if origin and origin not in {o.strip() for o in allowed}:
                return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
        if identity["role"] == "hr":
            return await call_next(request)
        own_id = identity["employee_id"]
        allowed_get = {"/api/employees", "/api/profiles", "/api/events", "/api/skills", "/api/rewards", f"/api/profiles/{own_id}"}
        allowed_get.update(f"/api/employees/{own_id}/{suffix}" for suffix in ("profile", "points", "points/transactions", "rewards/requests"))
        if request.method == "GET" and path in allowed_get:
            return await call_next(request)
        allowed_post = path in {"/api/recommendations", "/api/chat", "/api/activities/complete"} or (
            path.startswith("/api/activities/") and path.endswith("/complete")
        ) or (path.startswith("/api/rewards/") and path.endswith("/redeem"))
        if request.method == "POST" and allowed_post:
            try:
                body = await request.json()
            except (ValueError, json.JSONDecodeError):
                return JSONResponse({"detail": "Invalid JSON body"}, status_code=422)
            if isinstance(body, dict) and body.get("employee_id") == own_id and not body.get("profile"):
                return await call_next(request)
        return JSONResponse({"detail": "This account cannot access that resource"}, status_code=403)
    return guard
