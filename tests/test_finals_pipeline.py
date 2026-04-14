import json
from pathlib import Path

from scripts.finals import run_finals_pipeline as pipeline_module


def test_run_finals_pipeline_writes_summary(monkeypatch, tmp_path):
    output_dir = tmp_path / "reports"

    fake_eval = output_dir / "agent_eval_latest.json"
    fake_kpi = output_dir / "kpi_dashboard_latest.json"
    fake_defense = output_dir / "defense_reports_summary.json"

    def fake_export_defense_reports(path: Path, *, kpi_days: int = 30):
        path.mkdir(parents=True, exist_ok=True)
        fake_eval.write_text("{}", encoding="utf-8")
        fake_kpi.write_text("{}", encoding="utf-8")
        fake_defense.write_text("{}", encoding="utf-8")
        return {"eval": fake_eval, "kpi": fake_kpi, "summary": fake_defense}

    def fake_run_release_checks(path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "all_ok": True,
            "passed_checks": 6,
            "total_checks": 6,
            "checks": [],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    monkeypatch.setattr(pipeline_module, "export_defense_reports", fake_export_defense_reports)
    monkeypatch.setattr(pipeline_module, "run_release_checks", fake_run_release_checks)

    result = pipeline_module.run_finals_pipeline(output_dir, kpi_days=14)
    assert result["all_ok"] is True

    summary_path = output_dir / "finals_pipeline_summary.json"
    assert summary_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["all_ok"] is True
    assert summary["kpi_days"] == 14
    assert summary["release_checks"]["passed_checks"] == 6
    assert summary["release_checks"]["total_checks"] == 6
    assert Path(summary["artifacts"]["finals_release_check_json"]).exists()

