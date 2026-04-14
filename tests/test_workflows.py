from datetime import datetime, timedelta, timezone

from app.models import ApprovalTask, FollowUpTask, MaintenanceRecord, Resource, ResourceItem, Transaction
from tests.conftest import login_as


def _borrow_payload(hours_from_now: int = 24, duration_hours: int = 2, quantity: int = 1):
    borrow_time = datetime.utcnow() + timedelta(hours=hours_from_now)
    return {
        "resource_id": 1,
        "action": "borrow",
        "quantity": quantity,
        "purpose": "course project",
        "project_name": "ProjectAlpha",
        "estimated_quantity": quantity,
        "note": "Need for prototype",
        "borrow_time": borrow_time.isoformat(),
        "expected_return_time": (borrow_time + timedelta(hours=duration_hours)).isoformat(),
    }


def test_student_borrow_application_keeps_inventory_until_approved(test_env):
    client = test_env["client"]
    session = test_env["SessionLocal"]()
    headers, _ = login_as(client, "student1", "123456")
    before_available = session.get(Resource, 1).available_count

    response = client.post("/transactions", json=test_env["borrow_payload"], headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["approval_status"] == "pending"
    assert data["resource_name"] == "3D Printer"

    session.expire_all()
    assert session.get(Resource, 1).available_count == before_available

    tx_list = client.get("/transactions", headers=headers)
    assert tx_list.status_code == 200
    assert tx_list.json()[0]["resource_name"] == "3D Printer"
    session.close()


def test_teacher_approval_reduces_inventory(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    response = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )
    assert response.status_code == 200

    session.expire_all()
    assert session.get(Resource, 1).available_count == 2
    assert session.query(ResourceItem).filter(ResourceItem.resource_id == 1).count() == 3
    session.close()


def test_overlapping_borrow_allowed_when_capacity_not_exceeded(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    first = client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    assert first.status_code == 200
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    approved = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )
    assert approved.status_code == 200

    # Same slot, resource total_count=3: second request should still be accepted.
    second = client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    assert second.status_code == 200
    assert second.json()["status"] == "pending"
    assert second.json()["approval_status"] == "pending"


def test_overlapping_borrow_blocked_when_capacity_exceeded(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    full_payload = dict(test_env["borrow_payload"])
    full_payload["quantity"] = 3
    first = client.post("/transactions", json=full_payload, headers=student_headers)
    assert first.status_code == 200
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    approved = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )
    assert approved.status_code == 200

    second = client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    assert second.status_code == 400
    assert "capacity" in second.json()["detail"].lower()


def test_teacher_rejection_keeps_inventory(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    before_available = session.get(Resource, 2).available_count
    response = client.post("/transactions", json=test_env["consume_payload"], headers=student_headers)
    assert response.status_code == 200

    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    reject = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": False, "reason": "not needed"},
        headers=teacher_headers,
    )
    assert reject.status_code == 200

    session.expire_all()
    assert session.get(Resource, 2).available_count == before_available
    tx = session.get(Transaction, response.json()["id"])
    assert tx.status == "rejected"
    session.close()


def test_admin_direct_inventory_adjustment_success(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    session = test_env["SessionLocal"]()

    response = client.post(
        "/resources/2/inventory-adjustments",
        json={"target_total_count": 26, "target_available_count": 23, "reason": "restock"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "adjust"
    assert data["inventory_before_total"] == 20
    assert data["inventory_after_total"] == 26

    session.expire_all()
    resource = session.get(Resource, 2)
    assert resource.total_count == 26
    assert resource.available_count == 23
    session.close()


def test_admin_inventory_adjustment_only_available_change_succeeds(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    session = test_env["SessionLocal"]()

    response = client.post(
        "/resources/2/inventory-adjustments",
        json={"target_total_count": 20, "target_available_count": 18, "reason": "material recount"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "adjust"
    assert data["inventory_before_total"] == 20
    assert data["inventory_after_total"] == 20
    assert data["inventory_before_available"] == 20
    assert data["inventory_after_available"] == 18

    session.expire_all()
    resource = session.get(Resource, 2)
    assert resource.total_count == 20
    assert resource.available_count == 18
    session.close()


def test_admin_direct_inventory_adjustment_success_for_tracked_device(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    session = test_env["SessionLocal"]()

    response = client.post(
        "/resources/1/inventory-adjustments",
        json={"target_total_count": 2, "target_available_count": 2, "reason": "maintenance consolidation"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "adjust"
    assert data["inventory_before_total"] == 3
    assert data["inventory_after_total"] == 2
    assert data["inventory_after_available"] == 2

    session.expire_all()
    resource = session.get(Resource, 1)
    assert resource.total_count == 2
    assert resource.available_count == 2
    active_items = session.query(ResourceItem).filter(ResourceItem.resource_id == 1, ResourceItem.status != "disabled").count()
    assert active_items == 2
    session.close()


def test_admin_can_archive_resource_and_list_hides_disabled_by_default(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    student_headers, _ = login_as(client, "student1", "123456")
    session = test_env["SessionLocal"]()

    created = client.post(
        "/resources",
        json={
            "name": "Temp Jig",
            "category": "material",
            "subtype": "fixture",
            "location": "Shelf B",
            "total_count": 5,
            "available_count": 5,
            "unit_cost": 10,
            "min_threshold": 1,
            "status": "active",
            "description": "for archive test",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200
    resource_id = created.json()["id"]

    archived = client.delete(f"/resources/{resource_id}", headers=admin_headers)
    assert archived.status_code == 200

    blocked_use = client.post(
        "/transactions",
        json={
            "resource_id": resource_id,
            "action": "consume",
            "quantity": 1,
            "purpose": "should fail",
            "note": "archived",
        },
        headers=student_headers,
    )
    assert blocked_use.status_code == 400
    assert "archived" in blocked_use.json()["detail"].lower()

    default_list = client.get("/resources", headers=admin_headers)
    assert default_list.status_code == 200
    assert all(item["id"] != resource_id for item in default_list.json())

    include_disabled = client.get("/resources?include_disabled=true", headers=admin_headers)
    assert include_disabled.status_code == 200
    disabled_item = next(item for item in include_disabled.json() if item["id"] == resource_id)
    assert disabled_item["status"] == "disabled"

    session.expire_all()
    archived_resource = session.get(Resource, resource_id)
    assert archived_resource.status == "disabled"
    assert archived_resource.total_count == 5
    assert archived_resource.available_count == 5
    session.close()


def test_admin_can_restore_archived_resource(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    session = test_env["SessionLocal"]()

    created = client.post(
        "/resources",
        json={
            "name": "Temp Board",
            "category": "material",
            "subtype": "pcb",
            "location": "Shelf C",
            "total_count": 8,
            "available_count": 6,
            "unit_cost": 2,
            "min_threshold": 1,
            "status": "active",
            "description": "for restore test",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200
    resource_id = created.json()["id"]

    archived = client.delete(f"/resources/{resource_id}", headers=admin_headers)
    assert archived.status_code == 200

    restored = client.post(f"/resources/{resource_id}/restore", headers=admin_headers)
    assert restored.status_code == 200
    restored_data = restored.json()
    assert restored_data["status"] == "active"
    assert restored_data["total_count"] == 8
    assert restored_data["available_count"] == 6

    default_list = client.get("/resources", headers=admin_headers)
    assert default_list.status_code == 200
    assert any(item["id"] == resource_id for item in default_list.json())

    session.expire_all()
    restored_resource = session.get(Resource, resource_id)
    assert restored_resource.status == "active"
    assert restored_resource.total_count == 8
    assert restored_resource.available_count == 6
    session.close()


def test_student_cannot_approve(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)

    session = test_env["SessionLocal"]()
    approval_id = session.query(ApprovalTask.id).first()[0]
    session.close()

    response = client.post(
        f"/approvals/{approval_id}/approve",
        json={"approved": True, "reason": "hack"},
        headers=student_headers,
    )
    assert response.status_code == 403


def test_teacher_can_view_pending_approvals(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    response = client.get("/approvals?status=pending", headers=teacher_headers)
    assert response.status_code == 200
    item = response.json()[0]
    assert item["requester_name"] == "Student Zhang"
    assert item["resource_name"] == "3D Printer"
    assert item["action"] == "borrow"
    assert item["quantity"] == 1


def test_future_approved_borrow_is_not_returnable_yet(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    tx_response = client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    assert tx_response.status_code == 200
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    approved = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )
    assert approved.status_code == 200

    tx_list = client.get("/transactions", headers=student_headers)
    assert tx_list.status_code == 200
    item = next(tx for tx in tx_list.json() if tx["id"] == tx_response.json()["id"])
    assert item["status"] == "approved"
    assert item["can_return"] is False


def test_return_own_borrow_record_restores_inventory(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    payload = _borrow_payload(hours_from_now=-4, duration_hours=2, quantity=1)
    tx_response = client.post("/transactions", json=payload, headers=student_headers)
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )

    returned = client.patch(
        f"/transactions/{tx_response.json()['id']}/return",
        json={
            "condition_return": "good",
            "note": "all good",
            "return_time": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        },
        headers=student_headers,
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"

    session.expire_all()
    assert session.get(Resource, 1).available_count == 3
    session.close()


def test_return_supports_timezone_aware_return_time(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    payload = _borrow_payload(hours_from_now=-3, duration_hours=2, quantity=1)
    tx_response = client.post("/transactions", json=payload, headers=student_headers)
    assert tx_response.status_code == 200
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    approved = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )
    assert approved.status_code == 200

    # Frontend uses new Date().toISOString(), which is timezone-aware (UTC offset).
    aware_return_time = datetime.now(timezone.utc).isoformat()
    returned = client.patch(
        f"/transactions/{tx_response.json()['id']}/return",
        json={"condition_return": "good", "return_time": aware_return_time},
        headers=student_headers,
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"


def test_damaged_return_moves_item_to_quarantine_and_creates_maintenance(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    payload = _borrow_payload(hours_from_now=-6, duration_hours=3, quantity=1)
    tx_response = client.post("/transactions", json=payload, headers=student_headers)
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )

    returned = client.patch(
        f"/transactions/{tx_response.json()['id']}/return",
        json={
            "condition_return": "damaged",
            "note": "screen cracked",
            "return_time": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "evidence_url": "qiniu://damage/photo-1.jpg",
            "evidence_type": "image",
        },
        headers=student_headers,
    )
    assert returned.status_code == 200

    session.expire_all()
    resource = session.get(Resource, 1)
    assert resource.available_count == 2
    item = session.query(ResourceItem).filter(ResourceItem.resource_id == 1, ResourceItem.status == "quarantine").first()
    assert item is not None
    assert session.query(MaintenanceRecord).count() == 1
    assert session.query(FollowUpTask).filter(FollowUpTask.task_type == "maintenance").count() >= 1
    session.close()


def test_partial_lost_return_reduces_total_and_creates_followups(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    payload = _borrow_payload(hours_from_now=-8, duration_hours=4, quantity=2)
    tx_response = client.post("/transactions", json=payload, headers=student_headers)
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )

    returned = client.patch(
        f"/transactions/{tx_response.json()['id']}/return",
        json={
            "condition_return": "partial_lost",
            "lost_quantity": 1,
            "note": "one accessory missing",
            "return_time": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        },
        headers=student_headers,
    )
    assert returned.status_code == 200

    session.expire_all()
    resource = session.get(Resource, 1)
    assert resource.total_count == 2
    assert resource.available_count == 2
    task_types = {task.task_type for task in session.query(FollowUpTask).all()}
    assert {"accountability", "registry_backfill", "evidence_backfill"}.issubset(task_types)
    session.close()


def test_loss_registration_without_evidence_creates_backfill_task(test_env):
    client = test_env["client"]
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    created = client.post(
        "/transactions",
        json={
            "resource_id": 2,
            "action": "lost",
            "quantity": 1,
            "purpose": "loss registration",
            "note": "missing after workshop",
        },
        headers=teacher_headers,
    )
    assert created.status_code == 200

    session.expire_all()
    task_types = {task.task_type for task in session.query(FollowUpTask).all()}
    assert "evidence_backfill" in task_types
    session.close()


def test_return_time_before_borrow_time_is_rejected(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    payload = _borrow_payload(hours_from_now=10, duration_hours=2, quantity=1)
    tx_response = client.post("/transactions", json=payload, headers=student_headers)
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )

    returned = client.patch(
        f"/transactions/{tx_response.json()['id']}/return",
        json={
            "condition_return": "good",
            "return_time": datetime.utcnow().isoformat(),
        },
        headers=student_headers,
    )
    assert returned.status_code == 400
    assert "return_time" in returned.json()["detail"]


def test_failed_submit_does_not_dirty_write(test_env):
    client = test_env["client"]
    headers, _ = login_as(client, "student1", "123456")
    session = test_env["SessionLocal"]()

    before_tx = session.query(Transaction).count()
    before_approval = session.query(ApprovalTask).count()

    bad_payload = dict(test_env["borrow_payload"])
    bad_payload.pop("expected_return_time")
    response = client.post("/transactions", json=bad_payload, headers=headers)
    assert response.status_code == 400

    session.expire_all()
    assert session.query(Transaction).count() == before_tx
    assert session.query(ApprovalTask).count() == before_approval
    session.close()


def test_scheduler_slots_include_fairness_fields(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    response = client.post(
        "/scheduler/optimal-slots",
        json={
            "resource_id": 1,
            "duration_minutes": 120,
            "preferred_start": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        },
        headers=student_headers,
    )
    assert response.status_code == 200
    slots = response.json()["optimal_slots"]
    assert len(slots) > 0
    assert "fairness_penalty" in slots[0]
    assert "fairness_reasons" in slots[0]


def test_admin_can_update_fairness_policy_and_trigger_penalty(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    baseline = client.get("/scheduler/fairness-policy", headers=admin_headers)
    assert baseline.status_code == 200
    original_policy = baseline.json()

    try:
        created = client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
        assert created.status_code == 200
        approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
        approved = client.post(
            f"/approvals/{approval['id']}/approve",
            json={"approved": True, "reason": "seed fairness usage"},
            headers=teacher_headers,
        )
        assert approved.status_code == 200

        updated = client.patch(
            "/scheduler/fairness-policy",
            json={
                "enabled": True,
                "golden_hours_enabled": False,
                "consecutive_limit_enabled": False,
                "high_freq_penalty_enabled": True,
                "weekly_borrow_threshold": 1,
                "high_freq_penalty": 25,
            },
            headers=admin_headers,
        )
        assert updated.status_code == 200
        assert updated.json()["weekly_borrow_threshold"] == 1
        assert updated.json()["high_freq_penalty"] == 25.0

        slots = client.post(
            "/scheduler/optimal-slots",
            json={
                "resource_id": 1,
                "duration_minutes": 120,
                "preferred_start": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=student_headers,
        )
        assert slots.status_code == 200
        penalties = [item["fairness_penalty"] for item in slots.json()["optimal_slots"]]
        assert any(value >= 25.0 for value in penalties)
    finally:
        rollback_payload = {k: v for k, v in original_policy.items() if k != "updated_at"}
        client.patch("/scheduler/fairness-policy", json=rollback_payload, headers=admin_headers)


def test_non_admin_cannot_update_fairness_policy(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    response = client.patch(
        "/scheduler/fairness-policy",
        json={"weekly_borrow_threshold": 3},
        headers=student_headers,
    )
    assert response.status_code == 403
