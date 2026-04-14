"""Export reproducible defense reports for finals presentation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi.testclient import TestClient

from agent_eval.run_eval import run_agent_eval
from app.main import app


def _try_login(client: TestClient) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    candidates = [
        ("teacher1", "123456"),
        ("admin", "admin123"),
    ]
    for username, password in candidates:
        response = client.post("/auth/login", json={"username": username, "password": password})
        if response.status_code == 200:
            token = response.json()["token"]
            return {"Authorization": token}, username
    return None, None


def export_defense_reports(output_dir: Path, *, kpi_days: int = 30) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_report = run_agent_eval()
    eval_path = output_dir / "agent_eval_latest.json"
    eval_path.write_text(json.dumps(eval_report, ensure_ascii=False, indent=2), encoding="utf-8")

    with TestClient(app) as client:
        headers, login_user = _try_login(client)
        if not headers:
            raise RuntimeError(
                "Failed to login as teacher1/admin for KPI export. "
                "Please run `python -m app.seed_scenarios` first."
            )

        kpi_resp = client.get(f"/analytics/kpi-dashboard?days={int(kpi_days)}", headers=headers)
        if kpi_resp.status_code != 200:
            raise RuntimeError(
                f"KPI export failed: HTTP {kpi_resp.status_code} {kpi_resp.text[:200]}"
            )
        kpi_data = kpi_resp.json()
        kpi_data["exported_by"] = login_user
        kpi_data["exported_at"] = datetime.utcnow().isoformat() + "Z"

    kpi_path = output_dir / "kpi_dashboard_latest.json"
    kpi_path.write_text(json.dumps(kpi_data, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "agent_eval_score": eval_report["summary"]["score"],
        "agent_eval_passed": eval_report["summary"]["passed_cases"],
        "agent_eval_total": eval_report["summary"]["total_cases"],
        "kpi_days": int(kpi_days),
        "kpi_metric_count": len(kpi_data.get("metrics", [])),
        "artifacts": {
            "agent_eval_latest_json": str(eval_path),
            "kpi_dashboard_latest_json": str(kpi_path),
        },
    }
    summary_path = output_dir / "defense_reports_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "eval": eval_path,
        "kpi": kpi_path,
        "summary": summary_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export finals defense reports.")
    parser.add_argument(
        "--output-dir",
        default="docs/reports",
        help="Output directory for exported JSON reports.",
    )
    parser.add_argument(
        "--kpi-days",
        type=int,
        default=30,
        help="KPI window size in days (forwarded to /analytics/kpi-dashboard).",
    )
    args = parser.parse_args()

    artifacts = export_defense_reports(Path(args.output_dir), kpi_days=args.kpi_days)
    print("[defense-reports] generated:")
    print(f"  - {artifacts['eval']}")
    print(f"  - {artifacts['kpi']}")
    print(f"  - {artifacts['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

