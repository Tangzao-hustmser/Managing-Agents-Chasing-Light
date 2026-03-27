from datetime import datetime, timedelta

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
    assert {"accountability", "registry_backfill"}.issubset(task_types)
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
