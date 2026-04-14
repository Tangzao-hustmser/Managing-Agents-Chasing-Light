from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_p3_3_defense_asset_files_exist():
    required = [
        "docs/finals/2026-04-12-defense-evidence-chain.md",
        "docs/finals/2026-04-12-defense-ppt-outline.md",
        "docs/finals/2026-04-12-defense-ppt.md",
        "docs/finals/2026-04-12-defense-demo-script.md",
        "docs/finals/2026-04-12-competition-requirements-checklist.md",
        "scripts/finals/export_defense_reports.py",
        "scripts/finals/run_release_checks.py",
        "scripts/finals/run_finals_pipeline.py",
    ]
    for rel_path in required:
        assert Path(rel_path).exists(), f"Missing defense asset: {rel_path}"


def test_evidence_doc_contains_required_artifacts_and_sections():
    content = _read("docs/finals/2026-04-12-defense-evidence-chain.md")
    assert "问题-方案-结果映射" in content
    assert "```mermaid" in content
    assert "agent_eval_latest.json" in content
    assert "kpi_dashboard_latest.json" in content
    assert "finals_release_check.json" in content
    assert "finals_pipeline_summary.json" in content


def test_demo_script_mentions_one_command_pipeline_and_reports():
    content = _read("docs/finals/2026-04-12-defense-demo-script.md")
    assert "8-10 分钟" in content
    assert "run_finals_pipeline" in content
    assert "system/readiness" in content
    assert "agent_eval_latest.json" in content
    assert "kpi_dashboard_latest.json" in content


def test_competition_requirements_checklist_covers_all_four_rules():
    content = _read("docs/finals/2026-04-12-competition-requirements-checklist.md")
    assert "要求 R1" in content
    assert "要求 R2" in content
    assert "要求 R3" in content
    assert "要求 R4" in content
    assert "run_finals_pipeline" in content

