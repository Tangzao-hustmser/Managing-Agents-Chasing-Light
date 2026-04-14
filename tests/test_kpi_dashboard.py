from datetime import datetime, timedelta

from app.models import Transaction
from tests.conftest import login_as


def test_kpi_dashboard_requires_teacher_or_admin(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    forbidden = client.get("/analytics/kpi-dashboard", headers=student_headers)
    assert forbidden.status_code == 403


def test_kpi_dashboard_returns_metric_dictionary_and_values(test_env):
    client = test_env["client"]
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    response = client.get("/analytics/kpi-dashboard?days=30", headers=teacher_headers)
    assert response.status_code == 200
    data = response.json()

    metric_ids = {item["id"] for item in data["metrics"]}
    assert metric_ids == {
        "utilization_rate",
        "overdue_rate",
        "waste_rate",
        "loss_rate",
        "fairness_index",
    }
    dictionary_ids = {item["id"] for item in data["dictionary"]}
    assert metric_ids == dictionary_ids

    sample = data["metrics"][0]
    assert "baseline_value" in sample
    assert "current_value" in sample
    assert "improvement_value" in sample
    assert "improvement_percent" in sample
    assert "interpretation" in sample


def test_kpi_dashboard_utilization_improvement_reflects_baseline_comparison(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    session = test_env["SessionLocal"]()

    now = datetime.utcnow()
    tx = Transaction(
        resource_id=1,
        user_id=3,
        action="borrow",
        quantity=1,
        status="returned",
        is_approved=True,
        inventory_applied=True,
        borrow_time=now - timedelta(days=5, hours=3),
        expected_return_time=now - timedelta(days=5, hours=1),
        return_time=now - timedelta(days=5, hours=1),
        created_at=now - timedelta(days=5),
    )
    session.add(tx)
    session.commit()
    session.close()

    response = client.get("/analytics/kpi-dashboard?days=30", headers=admin_headers)
    assert response.status_code == 200
    metrics = {item["id"]: item for item in response.json()["metrics"]}
    utilization = metrics["utilization_rate"]
    assert utilization["current_value"] > utilization["baseline_value"]
    assert utilization["improvement_value"] > 0
    assert utilization["trend"] == "improved"
