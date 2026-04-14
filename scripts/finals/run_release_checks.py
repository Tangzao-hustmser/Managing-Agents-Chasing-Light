"""Finals release acceptance checks for end-to-end reproducibility."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agent_eval.run_eval import run_agent_eval
from app.database import ensure_database_schema, get_db
from app.main import app
from app.models import Resource, User
from app.services.auth_service import hash_password
from app.services.rate_limit_service import clear_rate_limit_cache


def _seed_release_check_data(db: Session) -> None:
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
                name="PLA Material",
                category="material",
                subtype="consumable",
                total_count=20,
                available_count=20,
                min_threshold=5,
                location="Shelf A",
            ),
        ]
    )
    db.commit()


def _login(client: TestClient, username: str, password: str) -> Tuple[Dict[str, str], Dict[str, Any]]:
    resp = client.post("/auth/login", json={"username": username, "password": password})
    if resp.status_code != 200:
        raise RuntimeError(f"Login failed for {username}: HTTP {resp.status_code} {resp.text[:200]}")
    data = resp.json()
    return {"Authorization": data["token"]}, data["user"]


def _append_check(
    checks: List[Dict[str, Any]],
    name: str,
    ok: bool,
    detail: str,
    data: Dict[str, Any] | None = None,
) -> None:
    checks.append(
        {
            "name": name,
            "ok": bool(ok),
            "detail": detail,
            "data": data or {},
        }
    )


def run_release_checks(output: Path | str) -> Dict[str, Any]:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    checks: List[Dict[str, Any]] = []

    agent_eval_report = run_agent_eval()
    eval_score = float(agent_eval_report["summary"]["score"])
    _append_check(
        checks,
        name="agent_eval_regression",
        ok=eval_score >= 100.0,
        detail=f"agent_eval score={eval_score:.2f}",
        data=agent_eval_report["summary"],
    )

    readiness_ok = False
    propose_ok = False
    confirm_ok = False
    enhanced_ok = False
    kpi_ok = False
    analysis_steps_ok = False

    clear_rate_limit_cache()
    with tempfile.TemporaryDirectory(prefix="release_checks_") as temp_dir:
        db_path = Path(temp_dir) / "release_check.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        ensure_database_schema(engine)

        seed_session = session_local()
        try:
            _seed_release_check_data(seed_session)
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
                teacher_headers, _ = _login(client, "teacher1", "123456")
                student_headers, _ = _login(client, "student1", "123456")

                readiness_resp = client.get("/system/readiness?probe_llm=false", headers=teacher_headers)
                readiness_ok = readiness_resp.status_code == 200 and "readiness_score" in readiness_resp.json()
                _append_check(
                    checks,
                    name="readiness_endpoint",
                    ok=readiness_ok,
                    detail=f"HTTP {readiness_resp.status_code}",
                    data=readiness_resp.json() if readiness_resp.status_code == 200 else {},
                )

                propose_resp = client.post(
                    "/agent/chat",
                    json={"message": "帮我申请借用 3D Printer 1台 明天下午 2小时 项目 Alpha"},
                    headers=student_headers,
                )
                propose_payload = propose_resp.json() if propose_resp.status_code == 200 else {}
                analysis_steps_ok = (
                    isinstance(propose_payload.get("analysis_steps"), list)
                    and len(propose_payload.get("analysis_steps", [])) >= 2
                )
                propose_ok = (
                    propose_resp.status_code == 200
                    and propose_payload.get("confirmation_required") is True
                    and (propose_payload.get("pending_action") or {}).get("name") == "submit_borrow_application"
                    and analysis_steps_ok
                )
                _append_check(
                    checks,
                    name="agent_action_proposal",
                    ok=propose_ok,
                    detail=f"HTTP {propose_resp.status_code}",
                    data={
                        "confirmation_required": propose_payload.get("confirmation_required"),
                        "pending_action_name": (propose_payload.get("pending_action") or {}).get("name"),
                        "analysis_steps_len": len(propose_payload.get("analysis_steps", [])),
                    },
                )

                if propose_resp.status_code == 200 and propose_payload.get("session_id"):
                    confirm_resp = client.post(
                        "/agent/chat",
                        json={"message": "确认", "session_id": propose_payload["session_id"]},
                        headers=student_headers,
                    )
                    confirm_payload = confirm_resp.json() if confirm_resp.status_code == 200 else {}
                    confirm_ok = confirm_resp.status_code == 200 and any(
                        item.get("name") == "submit_borrow_application"
                        for item in (confirm_payload.get("executed_tools") or [])
                    )
                    _append_check(
                        checks,
                        name="agent_action_execution",
                        ok=confirm_ok,
                        detail=f"HTTP {confirm_resp.status_code}",
                        data={
                            "executed_tools": confirm_payload.get("executed_tools", []),
                        },
                    )
                else:
                    _append_check(
                        checks,
                        name="agent_action_execution",
                        ok=False,
                        detail="Skipped because action proposal failed",
                        data={},
                    )

                enhanced_resp = client.post(
                    "/enhanced-agent/ask",
                    json={"question": "请结合治理与证据情况给我建议"},
                    headers=teacher_headers,
                )
                enhanced_payload = enhanced_resp.json() if enhanced_resp.status_code == 200 else {}
                enhanced_ok = (
                    enhanced_resp.status_code == 200
                    and enhanced_payload.get("success") is True
                    and isinstance(enhanced_payload.get("multi_agent_trace"), list)
                    and len(enhanced_payload.get("multi_agent_trace", [])) >= 3
                )
                _append_check(
                    checks,
                    name="enhanced_multi_agent_trace",
                    ok=enhanced_ok,
                    detail=f"HTTP {enhanced_resp.status_code}",
                    data={
                        "trace_len": len(enhanced_payload.get("multi_agent_trace", [])),
                        "orchestration_summary": enhanced_payload.get("orchestration_summary", ""),
                    },
                )

                kpi_resp = client.get("/analytics/kpi-dashboard?days=30", headers=teacher_headers)
                kpi_payload = kpi_resp.json() if kpi_resp.status_code == 200 else {}
                kpi_ok = (
                    kpi_resp.status_code == 200
                    and isinstance(kpi_payload.get("metrics"), list)
                    and len(kpi_payload.get("metrics", [])) >= 5
                )
                _append_check(
                    checks,
                    name="kpi_dashboard",
                    ok=kpi_ok,
                    detail=f"HTTP {kpi_resp.status_code}",
                    data={
                        "metrics_count": len(kpi_payload.get("metrics", [])),
                    },
                )

                requirements = {
                    "r1_goal_oriented": bool(propose_ok and confirm_ok),
                    "r2_perceive_reason_act": bool(analysis_steps_ok and confirm_ok),
                    "r3_multi_agent_or_multi_modal": bool(enhanced_ok),
                    "r4_innovation_practical_feasible": bool(readiness_ok and kpi_ok and eval_score >= 100.0),
                }
                _append_check(
                    checks,
                    name="competition_requirements_4x",
                    ok=all(requirements.values()),
                    detail="Match against 4 mandatory competition requirements",
                    data=requirements,
                )
        finally:
            app.dependency_overrides.clear()
            clear_rate_limit_cache()
            engine.dispose()

    all_ok = all(item["ok"] for item in checks)
    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "all_ok": all_ok,
        "passed_checks": sum(1 for item in checks if item["ok"]),
        "total_checks": len(checks),
        "checks": checks,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run finals release acceptance checks.")
    parser.add_argument(
        "--output",
        default="docs/reports/finals_release_check.json",
        help="Path to write acceptance check report JSON.",
    )
    args = parser.parse_args()

    report = run_release_checks(args.output)
    print(
        "[release-checks] "
        f"all_ok={report['all_ok']} "
        f"passed={report['passed_checks']}/{report['total_checks']} "
        f"report={args.output}"
    )
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

