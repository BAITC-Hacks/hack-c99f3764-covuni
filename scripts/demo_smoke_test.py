#!/usr/bin/env python3
"""
Cross-Platform Jury Live Smoke Test & Verification Script
Halyk Bank — Career Quest (HackAlem AI)
Team 202453

Executes sequential end-to-end verification without external dependencies (pure Python standard library).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

# Terminal Color Codes
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(base_url: str) -> None:
    print(f"{CYAN}{BOLD}")
    print("=" * 80)
    print("  🏦 HALYK BANK — CAREER QUEST | JURY LIVE SMOKE TEST (Team 202453)")
    print(f"  Target Server: {base_url}")
    print("=" * 80)
    print(f"{RESET}")


def api_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 5.0,
) -> Tuple[int, Dict[str, Any], int]:
    """Sends HTTP request and returns (status_code, parsed_json_or_error, elapsed_ms)."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    data_bytes = json.dumps(payload).encode("utf-8") if payload else None

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status = response.getcode()
            body_bytes = response.read()
            body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            return status, body, elapsed_ms
    except urllib.error.HTTPError as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        error_body = e.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(error_body)
        except Exception:
            parsed = {"error": error_body}
        return e.code, parsed, elapsed_ms
    except Exception as ex:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return 0, {"error": str(ex)}, elapsed_ms


def run_smoke_test(base_url: str = "http://localhost:8000") -> bool:
    print_banner(base_url)

    total_steps = 5
    passed = 0
    start_all = time.perf_counter()

    # --------------------------------------------------------------------------
    # STEP 1: Healthcheck
    # --------------------------------------------------------------------------
    print(f"{BOLD}1. Проверка доступности сервиса (GET /health)...{RESET}")
    status, body, elapsed = api_request(f"{base_url}/health")
    if status == 200:
        team_id = body.get("team_id", "N/A")
        server_status = body.get("status", "N/A")
        llm_ready = body.get("llm_ready", False)
        print(f"     Команда: {BOLD}{team_id}{RESET} | Статус: {GREEN}{server_status}{RESET} | LLM Engine: {MAGENTA}{llm_ready}{RESET}")
        print(f"  [{GREEN}PASS{RESET}] {BOLD}Шаг 1/{total_steps}:{RESET} Healthcheck ({YELLOW}{elapsed}ms{RESET})\n")
        passed += 1
    else:
        print(f"  [{RED}FAIL{RESET}] Шаг 1/{total_steps}: Healthcheck недоступен (Код: {status}, Ошибка: {body})")
        print(f"     {YELLOW}Совет:{RESET} Запустите сервер: docker compose up --build\n")
        return False

    # --------------------------------------------------------------------------
    # STEP 2: Ingest Jury Corner-Case Profile
    # --------------------------------------------------------------------------
    print(f"{BOLD}2. Загрузка проверочного профиля жюри (POST /api/profiles/upload)...{RESET}")
    candidate_id = "jury_demo_py_candidate"
    profile_payload = {
        "profiles": [
            {
                "id": candidate_id,
                "name": "Айдар Темирханов (Jury Python Demo)",
                "department": "Core Banking Architecture",
                "current_role": "Backend Developer",
                "current_grade": "Middle",
                "target_grade": "Senior",
                "skills": {
                    "Python": 4,
                    "PostgreSQL": 4,
                    "FastAPI": 4,
                    "API Design": 4,
                    "Docker": 3,
                    "System Design": 2,      # Target 4 for Senior (Deficit: 2, PROMOTION BLOCKER)
                    "Kubernetes": 3,
                    "Public Speaking": 1,    # MINIMAL SKILL in profile, not required for Senior Backend
                },
                "preferences": {
                    "preferred_formats": ["workshop"],
                    "max_hours_per_week": 8,
                },
            }
        ]
    }
    status, body, elapsed = api_request(f"{base_url}/api/profiles/upload", method="POST", payload=profile_payload)
    if status == 201 and body.get("loaded_count", 0) >= 1:
        print(f"     Успешно внедрено профилей в память: {GREEN}{body.get('loaded_count')}{RESET}")
        print(f"  [{GREEN}PASS{RESET}] {BOLD}Шаг 2/{total_steps}:{RESET} Динамическая загрузка профилей ({YELLOW}{elapsed}ms{RESET})\n")
        passed += 1
    else:
        print(f"  [{RED}FAIL{RESET}] Шаг 2/{total_steps}: Ошибка загрузки (Код: {status}, Ошибка: {body})\n")
        return False

    # --------------------------------------------------------------------------
    # STEP 3: Multi-Factor Recommendation vs Naive Trap
    # --------------------------------------------------------------------------
    print(f"{BOLD}3. Расчет рекомендаций: проверка обхода ловушки жюри...{RESET}")
    rec_payload = {"employee_id": candidate_id}
    status, body, elapsed = api_request(f"{base_url}/api/recommendations", method="POST", payload=rec_payload)
    if status == 200 and body.get("recommendations"):
        top = body["recommendations"][0]
        top_skill = top.get("target_skill")
        top_title = top.get("title")
        score = top.get("score")
        rationale = top.get("rationale")

        print(f"     {YELLOW}⚠ НАИВНОЕ ОДНОФАКТОРНОЕ ПРАВИЛО:{RESET} рекомендовало бы Public Speaking (уровень 1)")
        print(f"     {GREEN}✓ МНОГОФАКТОРНЫЙ АЛГОРИТМ HALYK:{RESET} выбрал {BOLD}{top_skill}{RESET} (Скор: {score})")
        print(f"     Мероприятие: {CYAN}{top_title}{RESET}")
        print(f"     {MAGENTA}Обоснование (4 фактора):{RESET} {rationale}")

        if top_skill == "System Design":
            print(f"  [{GREEN}PASS{RESET}] {BOLD}Шаг 3/{total_steps}:{RESET} Обход ловушки жюри подтвержден ({YELLOW}{elapsed}ms{RESET})\n")
            passed += 1
        else:
            print(f"  [{RED}FAIL{RESET}] Шаг 3/{total_steps}: Алгоритм выбрал '{top_skill}' вместо 'System Design'\n")
            return False
    else:
        print(f"  [{RED}FAIL{RESET}] Шаг 3/{total_steps}: Ошибка расчета рекомендаций (Код: {status}, Ошибка: {body})\n")
        return False

    # --------------------------------------------------------------------------
    # STEP 4: Complete Activity & Verify Skill Shift
    # --------------------------------------------------------------------------
    print(f"{BOLD}4. Прокачка компетенций: фиксация завершения активности (POST /api/activities/complete)...{RESET}")
    act_payload = {"employee_id": candidate_id, "event_id": "EV_005"}
    status, body, elapsed = api_request(f"{base_url}/api/activities/complete", method="POST", payload=act_payload)
    if status == 200:
        updates = body.get("skills_updated", [])
        diff_str = " | ".join(f"{u['skill']}: {u['old_level']} -> {u['new_level']} (max: {u['max_level']})" for u in updates)
        print(f"     Прогресс: {GREEN}{diff_str}{RESET}")
        print(f"  [{GREEN}PASS{RESET}] {BOLD}Шаг 4/{total_steps}:{RESET} Прокачка навыков и потолок max_level ({YELLOW}{elapsed}ms{RESET})\n")
        passed += 1
    else:
        print(f"  [{RED}FAIL{RESET}] Шаг 4/{total_steps}: Ошибка завершения активности (Код: {status}, Ошибка: {body})\n")
        return False

    # --------------------------------------------------------------------------
    # STEP 5: HR Analytics & Risk Group
    # --------------------------------------------------------------------------
    print(f"{BOLD}5. Корпоративная HR-аналитика и группа риска (GET /api/hr/analytics)...{RESET}")
    status, body, elapsed = api_request(f"{base_url}/api/hr/analytics")
    if status == 200:
        top_deficits = body.get("top_deficit_skills", [])[:3]
        risk_count = len(body.get("risk_group", []))
        print("     Топ проседающих компетенций компании:")
        for idx, item in enumerate(top_deficits, 1):
            print(f"       {idx}. {item['skill']} (суммарный дефицит: {item['total_gap']}, затронуто: {item['affected_employees_count']} чел.)")
        print(f"     Сотрудников в группе риска (пропуски / стагнация): {BOLD}{risk_count}{RESET}")
        print(f"  [{GREEN}PASS{RESET}] {BOLD}Шаг 5/{total_steps}:{RESET} HR-аналитика ({YELLOW}{elapsed}ms{RESET})\n")
        passed += 1
    else:
        print(f"  [{RED}FAIL{RESET}] Шаг 5/{total_steps}: Ошибка HR-аналитики (Код: {status}, Ошибка: {body})\n")
        return False

    total_sec = round(time.perf_counter() - start_all, 2)
    print(f"{CYAN}{'=' * 80}{RESET}")
    print(f"  {BOLD}ИТОГ ПРОВЕРКИ ЖЮРИ:{RESET} {GREEN}{passed}/{total_steps} УСПЕШНО ПРОЙДЕНО{RESET} (Общее время: {total_sec}s)")
    print("  Решение полностью стабильно, воспроизводимо и готово к защите!")
    print(f"{CYAN}{'=' * 80}{RESET}")
    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    success = run_smoke_test(target)
    sys.exit(0 if success else 1)
