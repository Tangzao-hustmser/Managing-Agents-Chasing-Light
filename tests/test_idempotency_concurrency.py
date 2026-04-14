from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app.models import Resource, Transaction
from tests.conftest import login_as


def _past_borrow_payload(quantity: int = 1) -> dict:
    borrow_time = datetime.utcnow() - timedelta(hours=6)
    return {
        "resource_id": 1,
        "action": "borrow",
        "quantity": quantity,
        "purpose": "concurrency test",
        "project_name": "LoadTest",
        "estimated_quantity": quantity,
        "note": "prepare approved borrow",
        "borrow_time": borrow_time.isoformat(),
        "expected_return_time": (borrow_time + timedelta(hours=2)).isoformat(),
    }


def test_approve_endpoint_replays_response_when_idempotency_key_reused(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    created = client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    assert created.status_code == 200
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]

    request_headers = dict(teacher_headers)
    request_headers["Idempotency-Key"] = "approve-replay-001"
    first = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "approved once"},
        headers=request_headers,
    )
    second = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "approved once"},
        headers=request_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "approved"

    session.expire_all()
    assert session.get(Resource, 1).available_count == 2
    session.close()


def test_return_endpoint_replays_response_when_idempotency_key_reused(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    created = client.post("/transactions", json=_past_borrow_payload(), headers=student_headers)
    assert created.status_code == 200
    tx_id = created.json()["id"]
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    approved = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )
    assert approved.status_code == 200

    return_headers = dict(student_headers)
    return_headers["Idempotency-Key"] = "return-replay-001"
    payload = {
        "condition_return": "good",
        "note": "all good",
        "return_time": datetime.now(timezone.utc).isoformat(),
    }
    first = client.patch(f"/transactions/{tx_id}/return", json=payload, headers=return_headers)
    second = client.patch(f"/transactions/{tx_id}/return", json=payload, headers=return_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == tx_id
    assert second.json()["id"] == tx_id
    assert second.json()["status"] == "returned"

    session.expire_all()
    assert session.get(Resource, 1).available_count == 3
    session.close()


def test_inventory_adjustment_replays_response_with_same_idempotency_key(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    session = test_env["SessionLocal"]()

    request_headers = dict(admin_headers)
    request_headers["Idempotency-Key"] = "adjust-replay-001"
    payload = {"target_total_count": 26, "target_available_count": 23, "reason": "recount"}

    first = client.post("/resources/2/inventory-adjustments", json=payload, headers=request_headers)
    second = client.post("/resources/2/inventory-adjustments", json=payload, headers=request_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["inventory_after_total"] == 26
    assert second.json()["inventory_after_available"] == 23

    session.expire_all()
    resource = session.get(Resource, 2)
    assert resource.total_count == 26
    assert resource.available_count == 23
    assert session.query(Transaction).filter(Transaction.action == "adjust").count() == 1
    session.close()


def test_inventory_adjustment_idempotency_key_conflict_when_payload_changes(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")

    request_headers = dict(admin_headers)
    request_headers["Idempotency-Key"] = "adjust-conflict-001"

    first = client.post(
        "/resources/2/inventory-adjustments",
        json={"target_total_count": 24, "target_available_count": 22, "reason": "batch-1"},
        headers=request_headers,
    )
    second = client.post(
        "/resources/2/inventory-adjustments",
        json={"target_total_count": 25, "target_available_count": 23, "reason": "batch-2"},
        headers=request_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert "different payload" in second.json()["detail"].lower()


def test_concurrent_approve_requests_do_not_double_apply_inventory(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    created = client.post("/transactions", json=test_env["borrow_payload"], headers=student_headers)
    assert created.status_code == 200
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]

    def _approve_once() -> int:
        response = client.post(
            f"/approvals/{approval['id']}/approve",
            json={"approved": True, "reason": "parallel click"},
            headers=teacher_headers,
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = [future.result() for future in [pool.submit(_approve_once), pool.submit(_approve_once)]]

    assert sorted(statuses) == [200, 400]

    session.expire_all()
    assert session.get(Resource, 1).available_count == 2
    tx = session.get(Transaction, created.json()["id"])
    assert tx.status == "approved"
    assert tx.inventory_applied is True
    session.close()
