from datetime import datetime, timedelta

from app.models import FollowUpTask
from tests.conftest import login_as


def test_pending_approval_triggers_notification_log(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    created = client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    assert created.status_code == 200

    deliveries = client.get("/notifications/deliveries?event_type=approval_pending", headers=teacher_headers)
    assert deliveries.status_code == 200
    rows = deliveries.json()
    assert any(item["channel"] == "in_app" and item["status"] == "sent" for item in rows)


def test_low_inventory_alerts_are_deduplicated_with_occurrence_counter(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    first = client.post(
        "/resources/2/inventory-adjustments",
        json={"target_total_count": 20, "target_available_count": 4, "reason": "low inventory simulation 1"},
        headers=admin_headers,
    )
    assert first.status_code == 200

    second = client.post(
        "/resources/2/inventory-adjustments",
        json={"target_total_count": 20, "target_available_count": 3, "reason": "low inventory simulation 2"},
        headers=admin_headers,
    )
    assert second.status_code == 200

    alerts = client.get("/alerts?include_resolved=true", headers=teacher_headers)
    assert alerts.status_code == 200
    low_inventory = [item for item in alerts.json() if item["type"] == "low_inventory" and "resource:2" in item["dedup_key"]]
    assert len(low_inventory) == 1
    assert low_inventory[0]["occurrence_count"] >= 2


def test_follow_up_sla_overdue_triggers_notification_log(test_env):
    client = test_env["client"]
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    task = FollowUpTask(
        resource_id=1,
        assigned_user_id=2,
        task_type="maintenance",
        status="open",
        title="Notification SLA task",
        description="pending",
        due_at=datetime.utcnow() - timedelta(hours=3),
    )
    session.add(task)
    session.commit()
    session.close()

    listed = client.get("/follow-up-tasks?status=all&assigned=all", headers=teacher_headers)
    assert listed.status_code == 200

    deliveries = client.get("/notifications/deliveries?event_type=follow_up_sla_overdue", headers=teacher_headers)
    assert deliveries.status_code == 200
    rows = deliveries.json()
    assert any(item["channel"] == "in_app" and item["status"] == "sent" for item in rows)


def test_student_cannot_read_notification_deliveries(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    forbidden = client.get("/notifications/deliveries", headers=student_headers)
    assert forbidden.status_code == 403
