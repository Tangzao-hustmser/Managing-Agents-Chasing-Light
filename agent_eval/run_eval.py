"""Regression scoring runner for agent capability evaluation cases."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import ensure_database_schema, get_db
from app.main import app
from app.models import Resource, User
from app.services.auth_service import hash_password
from app.services.rate_limit_service import clear_rate_limit_cache

DEFAULT_DATASET_PATH = Path(__file__).with_name("cases.json")
DEFAULT_FAIL_UNDER = 100.0

ROLE_PASSWORDS: Dict[str, str] = {
    "admin": "admin123",
    "teacher1": "123456",
    "student1": "123456",
}


def _load_dataset(dataset_path: Path) -> Dict[str, Any]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {dataset_path}")
    raw = dataset_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data.get("cases"), list) or not data["cases"]:
        raise ValueError("Dataset must contain a non-empty 'cases' array")
    return data


def _seed_base_data(db: Session) -> None:
    db.add_all(
        [
            User(
                username="admin",
                password=hash_password("admin123"),
                real_name="Admin",
                student_id="A001",
                email="admin@test.local",
                role="admin",
                is_active=True,
            ),
            User(
                username="teacher1",
                password=hash_password("123456"),
                real_name="Teacher Wang",
                student_id="T001",
                email="teacher@test.local",
                role="teacher",
                is_active=True,
            ),
            User(
                username="student1",
                password=hash_password("123456"),
                real_name="Student Zhang",
                student_id="S001",
                email="student@test.local",
                role="student",
                is_active=True,
            ),
            Resource(
                name="3D Printer",
                category="device",
                subtype="printer",
                total_count=3,
                available_count=3,
                min_threshold=1,
                location="Room 101",
            ),
            Resource(
                name="Laser Cutter",
                category="device",
                subtype="cutter",
                total_count=2,
                available_count=2,
                min_threshold=1,
                location="Room 102",
            ),
            Resource(
                name="Multimeter",
                category="device",
                subtype="meter",
                total_count=6,
                available_count=5,
                min_threshold=2,
                location="Room 201",
            ),
            Resource(
                name="PLA Material",
                category="material",
                subtype="consumable",
                total_count=20,
                available_count=20,
                min_threshold=5,
                location="Shelf A",
            ),
            Resource(
                name="ESP32 Board",
                category="material",
                subtype="development_board",
                total_count=30,
                available_count=25,
                min_threshold=8,
                location="Shelf B",
            ),
        ]
    )
    db.commit()


def _login_headers(client: TestClient, username: str, password: str) -> Dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        raise RuntimeError(f"Failed to login as {username}: HTTP {response.status_code} {response.text}")
    return {"Authorization": response.json()["token"]}


@contextmanager
def _evaluation_environment() -> Iterator[Tuple[TestClient, Dict[str, Dict[str, str]]]]:
    clear_rate_limit_cache()
    with tempfile.TemporaryDirectory(prefix="agent_eval_") as temp_dir:
        db_path = Path(temp_dir) / "agent_eval.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        ensure_database_schema(engine)

        seed_session = session_local()
        try:
            _seed_base_data(seed_session)
        finally:
            seed_session.close()

        def override_get_db():
            db = session_local()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        try:
            with TestClient(app) as client:
                headers_by_role = {
                    role: _login_headers(client, role, password) for role, password in ROLE_PASSWORDS.items()
                }
                yield client, headers_by_role
        finally:
            app.dependency_overrides.clear()
            clear_rate_limit_cache()
            engine.dispose()


def _check_response_expectations(payload: Dict[str, Any], expect: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if "intent" in expect and payload.get("intent") != expect["intent"]:
        errors.append(f"intent mismatch: expected {expect['intent']}, got {payload.get('intent')}")

    if "confirmation_required" in expect and bool(payload.get("confirmation_required")) != bool(expect["confirmation_required"]):
        errors.append(
            "confirmation_required mismatch: "
            f"expected {expect['confirmation_required']}, got {payload.get('confirmation_required')}"
        )

    if expect.get("pending_action_absent") and payload.get("pending_action") is not None:
        errors.append("pending_action should be absent but returned")

    if "pending_action_name" in expect:
        pending_action = payload.get("pending_action") or {}
        if pending_action.get("name") != expect["pending_action_name"]:
            errors.append(
                f"pending_action.name mismatch: expected {expect['pending_action_name']}, got {pending_action.get('name')}"
            )

    executed_tools = payload.get("executed_tools") or []

    if "executed_tools_len" in expect and len(executed_tools) != int(expect["executed_tools_len"]):
        errors.append(f"executed_tools length mismatch: expected {expect['executed_tools_len']}, got {len(executed_tools)}")

    if "executed_tool_name" in expect and not any(tool.get("name") == expect["executed_tool_name"] for tool in executed_tools):
        errors.append(f"executed tool {expect['executed_tool_name']} not found")

    reply = str(payload.get("reply") or "")
    for token in expect.get("reply_contains", []):
        if token not in reply:
            errors.append(f"reply missing token: {token}")

    contains_any = expect.get("reply_contains_any", [])
    if contains_any and not any(token in reply for token in contains_any):
        errors.append(f"reply missing any expected tokens: {contains_any}")

    if "analysis_steps_min" in expect:
        steps = payload.get("analysis_steps") or []
        if len(steps) < int(expect["analysis_steps_min"]):
            errors.append(f"analysis_steps too short: expected >= {expect['analysis_steps_min']}, got {len(steps)}")

    if "used_model" in expect and bool(payload.get("used_model")) != bool(expect["used_model"]):
        errors.append(f"used_model mismatch: expected {expect['used_model']}, got {payload.get('used_model')}")

    return errors


def _evaluate_single_turn(case: Dict[str, Any], client: TestClient, headers: Dict[str, str]) -> List[str]:
    response = client.post("/agent/chat", json={"message": case["message"]}, headers=headers)
    expect = case.get("expect", {})
    expected_status = int(expect.get("status_code", 200))
    if response.status_code != expected_status:
        return [f"status mismatch: expected {expected_status}, got {response.status_code}"]

    payload = response.json()
    return _check_response_expectations(payload, expect)


def _evaluate_propose_confirm(case: Dict[str, Any], client: TestClient, headers: Dict[str, str]) -> List[str]:
    errors: List[str] = []

    proposed = client.post("/agent/chat", json={"message": case["propose_message"]}, headers=headers)
    if proposed.status_code != 200:
        return [f"proposal request failed: HTTP {proposed.status_code}"]
    proposed_payload = proposed.json()

    expected_pending_action = case["expected_pending_action"]
    expected_proposal = {
        "confirmation_required": True,
        "pending_action_name": expected_pending_action,
    }
    errors.extend(_check_response_expectations(proposed_payload, expected_proposal))

    session_id = proposed_payload.get("session_id")
    if not session_id:
        errors.append("missing session_id in proposal response")
        return errors

    confirm_body = {
        "message": case.get("confirm_message", "确认"),
        "session_id": session_id,
    }
    confirmed = client.post("/agent/chat", json=confirm_body, headers=headers)
    if confirmed.status_code != 200:
        errors.append(f"confirm request failed: HTTP {confirmed.status_code}")
        return errors

    confirmed_payload = confirmed.json()
    expected_confirm = {
        "confirmation_required": False,
        "pending_action_absent": True,
        "executed_tool_name": case["expected_executed_tool"],
    }
    errors.extend(_check_response_expectations(confirmed_payload, expected_confirm))

    return errors


def _evaluate_bad_confirmation_token(case: Dict[str, Any], client: TestClient, headers: Dict[str, str]) -> List[str]:
    errors: List[str] = []

    proposed = client.post("/agent/chat", json={"message": case["propose_message"]}, headers=headers)
    if proposed.status_code != 200:
        return [f"proposal request failed: HTTP {proposed.status_code}"]
    proposed_payload = proposed.json()

    expected_pending_action = case["expected_pending_action"]
    expected_proposal = {
        "confirmation_required": True,
        "pending_action_name": expected_pending_action,
    }
    errors.extend(_check_response_expectations(proposed_payload, expected_proposal))

    session_id = proposed_payload.get("session_id")
    if not session_id:
        errors.append("missing session_id in proposal response")
        return errors

    confirm_body = {
        "message": case.get("confirm_message", "确认"),
        "session_id": session_id,
        "confirmation_token": case.get("bad_confirmation_token", "invalid-token"),
    }
    confirmed = client.post("/agent/chat", json=confirm_body, headers=headers)
    expected_status = int(case.get("expected_status_code", 400))
    if confirmed.status_code != expected_status:
        errors.append(f"status mismatch: expected {expected_status}, got {confirmed.status_code}")
        return errors

    payload = confirmed.json()
    detail = str(payload.get("detail", ""))
    expect_contains = str(case.get("error_detail_contains", "")).lower()
    if expect_contains and expect_contains not in detail.lower():
        errors.append(f"error detail mismatch: expected to contain '{expect_contains}', got '{detail}'")

    return errors


def _evaluate_case(case: Dict[str, Any], client: TestClient, headers_by_role: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    role = case.get("role")
    headers = headers_by_role.get(role)
    if not headers:
        return {
            "id": case.get("id", "<unknown>"),
            "category": case.get("category", "unknown"),
            "passed": False,
            "errors": [f"unknown role: {role}"],
        }

    case_type = case.get("type", "single_turn")
    errors: List[str]
    try:
        if case_type == "single_turn":
            errors = _evaluate_single_turn(case, client, headers)
        elif case_type == "propose_confirm":
            errors = _evaluate_propose_confirm(case, client, headers)
        elif case_type == "bad_confirmation_token":
            errors = _evaluate_bad_confirmation_token(case, client, headers)
        else:
            errors = [f"unsupported case type: {case_type}"]
    except Exception as exc:  # pragma: no cover - defensive guard for evaluator robustness
        errors = [f"unexpected evaluator error: {exc}"]

    return {
        "id": case.get("id", "<unknown>"),
        "title": case.get("title", ""),
        "category": case.get("category", "unknown"),
        "type": case_type,
        "passed": not errors,
        "errors": errors,
    }


def _build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    failed = total - passed
    score = round((passed / total) * 100, 2) if total else 0.0

    category_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "score": 0.0})
    for item in results:
        stats = category_stats[item["category"]]
        stats["total"] += 1
        if item["passed"]:
            stats["passed"] += 1
        else:
            stats["failed"] += 1

    for stats in category_stats.values():
        stats["score"] = round((stats["passed"] / stats["total"]) * 100, 2) if stats["total"] else 0.0

    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": failed,
        "score": score,
        "category_scores": dict(sorted(category_stats.items())),
    }


def run_agent_eval(dataset_path: Path | str = DEFAULT_DATASET_PATH) -> Dict[str, Any]:
    dataset_path = Path(dataset_path)
    dataset = _load_dataset(dataset_path)
    cases = dataset["cases"]

    with _evaluation_environment() as (client, headers_by_role):
        results = [_evaluate_case(case, client, headers_by_role) for case in cases]

    summary = _build_summary(results)
    return {
        "dataset": str(dataset_path),
        "meta": dataset.get("meta", {}),
        "evaluated_at": datetime.utcnow().isoformat() + "Z",
        "summary": summary,
        "results": results,
    }


def _print_report(report: Dict[str, Any]) -> None:
    summary = report["summary"]
    print(
        "[agent-eval] "
        f"score={summary['score']:.2f} "
        f"passed={summary['passed_cases']}/{summary['total_cases']} "
        f"failed={summary['failed_cases']}"
    )
    print("[agent-eval] category scores:")
    for category, stats in summary["category_scores"].items():
        print(f"  - {category}: {stats['passed']}/{stats['total']} ({stats['score']:.2f})")

    failed = [item for item in report["results"] if not item["passed"]]
    if failed:
        print("[agent-eval] failed cases:")
        for item in failed:
            print(f"  - {item['id']}: {'; '.join(item['errors'])}")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run agent capability regression scoring.")
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Path to evaluation dataset JSON.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON report path.",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=DEFAULT_FAIL_UNDER,
        help="Fail (exit code 1) when score is below this threshold.",
    )
    args = parser.parse_args(argv)

    report = run_agent_eval(args.dataset)
    _print_report(report)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if report["summary"]["score"] < args.fail_under:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

