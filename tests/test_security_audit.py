from datetime import datetime, timedelta

from app.config import settings
from app.services.rate_limit_service import clear_rate_limit_cache
from tests.conftest import login_as


def _past_borrow_payload(quantity: int = 1) -> dict:
    borrow_time = datetime.utcnow() - timedelta(hours=5)
    return {
        "resource_id": 1,
        "action": "borrow",
        "quantity": quantity,
        "purpose": "audit flow",
        "project_name": "AuditProject",
        "estimated_quantity": quantity,
        "note": "audit borrow",
        "borrow_time": borrow_time.isoformat(),
        "expected_return_time": (borrow_time + timedelta(hours=2)).isoformat(),
    }


def test_key_write_actions_generate_audit_logs(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    admin_headers, _ = login_as(client, "admin", "admin123")

    created = client.post("/transactions", json=_past_borrow_payload(), headers=student_headers)
    assert created.status_code == 200
    tx_id = created.json()["id"]

    approval = client.get("/approvals?status=pending", headers=teacher_headers)
    assert approval.status_code == 200
    approval_id = approval.json()[0]["id"]
    approved = client.post(
        f"/approvals/{approval_id}/approve",
        json={"approved": True, "reason": "audit approve"},
        headers=teacher_headers,
    )
    assert approved.status_code == 200

    returned = client.patch(
        f"/transactions/{tx_id}/return",
        json={"condition_return": "good", "note": "audit return"},
        headers=student_headers,
    )
    assert returned.status_code == 200

    adjusted = client.post(
        "/resources/2/inventory-adjustments",
        json={"target_total_count": 20, "target_available_count": 18, "reason": "audit adjust"},
        headers={**admin_headers, "Idempotency-Key": "audit-adjust-001"},
    )
    assert adjusted.status_code == 200

    logs = client.get("/audit-logs?limit=200", headers=teacher_headers)
    assert logs.status_code == 200
    rows = logs.json()
    actions = {item["action"] for item in rows}
    assert "approval.approve" in actions
    assert "transaction.return" in actions
    assert "resource.inventory_adjustment" in actions
    adjustment_log = next(item for item in rows if item["action"] == "resource.inventory_adjustment")
    assert adjustment_log["idempotency_key"] == "audit-adjust-001"


def test_student_cannot_view_audit_logs(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    forbidden = client.get("/audit-logs", headers=student_headers)
    assert forbidden.status_code == 403


def test_rate_limit_blocks_repeated_inventory_adjustments(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")

    old_enabled = settings.rate_limit_enabled
    old_window = settings.rate_limit_window_seconds
    old_max = settings.rate_limit_max_requests

    clear_rate_limit_cache()
    settings.rate_limit_enabled = True
    settings.rate_limit_window_seconds = 60
    settings.rate_limit_max_requests = 2
    try:
        first = client.post(
            "/resources/2/inventory-adjustments",
            json={"target_total_count": 20, "target_available_count": 19, "reason": "rate-limit-1"},
            headers=admin_headers,
        )
        second = client.post(
            "/resources/2/inventory-adjustments",
            json={"target_total_count": 20, "target_available_count": 18, "reason": "rate-limit-2"},
            headers=admin_headers,
        )
        third = client.post(
            "/resources/2/inventory-adjustments",
            json={"target_total_count": 20, "target_available_count": 17, "reason": "rate-limit-3"},
            headers=admin_headers,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert "rate limit exceeded" in third.json()["detail"].lower()
    finally:
        settings.rate_limit_enabled = old_enabled
        settings.rate_limit_window_seconds = old_window
        settings.rate_limit_max_requests = old_max
        clear_rate_limit_cache()
