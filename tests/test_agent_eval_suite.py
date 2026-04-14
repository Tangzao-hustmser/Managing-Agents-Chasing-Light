import json
from pathlib import Path

from agent_eval.run_eval import DEFAULT_DATASET_PATH, run_agent_eval


def test_agent_eval_dataset_covers_required_categories():
    dataset = json.loads(Path(DEFAULT_DATASET_PATH).read_text(encoding="utf-8"))
    categories = {case["category"] for case in dataset["cases"]}
    assert {"qa", "execution", "refusal", "clarification", "exception"}.issubset(categories)


def test_agent_eval_runner_scores_full_mark_on_baseline():
    report = run_agent_eval(DEFAULT_DATASET_PATH)
    summary = report["summary"]
    assert summary["failed_cases"] == 0
    assert summary["passed_cases"] == summary["total_cases"]
    assert summary["score"] == 100.0

