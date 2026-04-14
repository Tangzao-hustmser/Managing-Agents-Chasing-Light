"""One-command finals pipeline for defense artifacts and acceptance checks."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from scripts.finals.export_defense_reports import export_defense_reports
from scripts.finals.run_release_checks import run_release_checks


def run_finals_pipeline(output_dir: Path | str, *, kpi_days: int = 30) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exported = export_defense_reports(output_dir, kpi_days=kpi_days)
    release_path = output_dir / "finals_release_check.json"
    release_report = run_release_checks(release_path)

    pipeline_summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "all_ok": bool(release_report.get("all_ok", False)),
        "kpi_days": int(kpi_days),
        "artifacts": {
            "agent_eval_latest_json": str(exported["eval"]),
            "kpi_dashboard_latest_json": str(exported["kpi"]),
            "defense_reports_summary_json": str(exported["summary"]),
            "finals_release_check_json": str(release_path),
        },
        "release_checks": {
            "passed_checks": int(release_report.get("passed_checks", 0)),
            "total_checks": int(release_report.get("total_checks", 0)),
        },
    }
    summary_path = output_dir / "finals_pipeline_summary.json"
    summary_path.write_text(json.dumps(pipeline_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "all_ok": pipeline_summary["all_ok"],
        "summary_path": summary_path,
        "pipeline_summary": pipeline_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one-command finals pipeline.")
    parser.add_argument(
        "--output-dir",
        default="docs/reports",
        help="Directory to store all generated finals reports.",
    )
    parser.add_argument(
        "--kpi-days",
        type=int,
        default=30,
        help="KPI window days used when exporting KPI dashboard.",
    )
    args = parser.parse_args()

    result = run_finals_pipeline(args.output_dir, kpi_days=args.kpi_days)
    print(
        "[finals-pipeline] "
        f"all_ok={result['all_ok']} "
        f"summary={result['summary_path']}"
    )
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

