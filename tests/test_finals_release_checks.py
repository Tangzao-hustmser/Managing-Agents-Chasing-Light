import json
from pathlib import Path

from scripts.finals.run_release_checks import run_release_checks


def test_run_release_checks_generates_all_green_report(tmp_path):
    output = tmp_path / "release_check.json"
    report = run_release_checks(output)

    assert report["all_ok"] is True
    assert report["passed_checks"] == report["total_checks"]
    assert report["total_checks"] >= 5
    assert output.exists()

    loaded = json.loads(Path(output).read_text(encoding="utf-8"))
    assert loaded["all_ok"] is True
    assert any(item["name"] == "agent_eval_regression" for item in loaded["checks"])
    assert any(item["name"] == "enhanced_multi_agent_trace" for item in loaded["checks"])
    req = next(item for item in loaded["checks"] if item["name"] == "competition_requirements_4x")
    assert req["ok"] is True
    assert set(req["data"].keys()) == {
        "r1_goal_oriented",
        "r2_perceive_reason_act",
        "r3_multi_agent_or_multi_modal",
        "r4_innovation_practical_feasible",
    }
