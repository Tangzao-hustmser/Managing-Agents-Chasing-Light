from datetime import datetime, timedelta

from app.models import FollowUpTask
from tests.conftest import login_as


def _borrow_payload(hours_from_now: int = -6, duration_hours: int = 2, quantity: int = 2):
    borrow_time = datetime.utcnow() + timedelta(hours=hours_from_now)
    return {
        "resource_id": 1,
        "action": "borrow",
        "quantity": quantity,
        "purpose": "course project",
        "project_name": "ProjectOmega",
        "estimated_quantity": quantity,
        "note": "Need for prototype",
        "borrow_time": borrow_time.isoformat(),
        "expected_return_time": (borrow_time + timedelta(hours=duration_hours)).isoformat(),
    }


def test_follow_up_tasks_student_can_list_and_update_assigned_task(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    created = client.post("/transactions", json=_borrow_payload(), headers=student_headers)
    assert created.status_code == 200
    approval = client.get("/approvals?status=pending", headers=teacher_headers).json()[0]
    approved = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"approved": True, "reason": "ok"},
        headers=teacher_headers,
    )
    assert approved.status_code == 200

    returned = client.patch(
        f"/transactions/{created.json()['id']}/return",
        json={
            "condition_return": "partial_lost",
            "lost_quantity": 1,
            "note": "one accessory missing",
            "return_time": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        },
        headers=student_headers,
    )
    assert returned.status_code == 200

    listed = client.get("/follow-up-tasks?status=all", headers=student_headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert any(item["task_type"] == "accountability" for item in rows)

    editable = next(item for item in rows if item["can_update"])
    updated = client.patch(
        f"/follow-up-tasks/{editable['id']}",
        json={"status": "done", "note": "处理完成"},
        headers=student_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"
    assert "处理完成" in updated.json()["description"]

    teacher_view = client.get("/follow-up-tasks?status=all&assigned=all", headers=teacher_headers)
    assert teacher_view.status_code == 200
    assert any(item["id"] == editable["id"] and item["status"] == "done" for item in teacher_view.json())


def test_student_cannot_update_unassigned_follow_up_task(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    session = test_env["SessionLocal"]()
    task = FollowUpTask(
        resource_id=1,
        assigned_user_id=2,  # teacher1
        task_type="maintenance",
        status="open",
        title="Teacher-owned maintenance follow-up",
        description="do not allow student update",
        due_at=datetime.utcnow() + timedelta(days=1),
    )
    session.add(task)
    session.commit()
    task_id = task.id
    session.close()

    forbidden = client.patch(
        f"/follow-up-tasks/{task_id}",
        json={"status": "done", "note": "try update"},
        headers=student_headers,
    )
    assert forbidden.status_code == 403

    listed = client.get("/follow-up-tasks?status=all", headers=student_headers)
    assert listed.status_code == 200
    assert task_id not in [item["id"] for item in listed.json()]


def test_agent_chat_can_confirm_and_update_follow_up_task(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    session = test_env["SessionLocal"]()
    task = FollowUpTask(
        resource_id=1,
        assigned_user_id=3,  # student1
        task_type="accountability",
        status="open",
        title="Student accountability follow-up",
        description="pending",
        due_at=datetime.utcnow() + timedelta(days=1),
    )
    session.add(task)
    session.commit()
    task_id = task.id
    session.close()

    proposed = client.post(
        "/agent/chat",
        json={"message": f"完成任务 #{task_id}"},
        headers=student_headers,
    )
    assert proposed.status_code == 200
    data = proposed.json()
    assert data["confirmation_required"] is True
    assert data["pending_action"]["name"] == "update_follow_up_task"

    confirmed = client.post(
        "/agent/chat",
        json={"message": "确认", "session_id": data["session_id"]},
        headers=student_headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["executed_tools"][0]["name"] == "update_follow_up_task"

    checked = client.get("/follow-up-tasks?status=all", headers=student_headers)
    assert checked.status_code == 200
    assert any(item["id"] == task_id and item["status"] == "done" for item in checked.json())


def test_agent_chat_supports_context_task_reference_without_explicit_id(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    session = test_env["SessionLocal"]()
    task = FollowUpTask(
        resource_id=1,
        assigned_user_id=3,
        task_type="maintenance",
        status="open",
        title="Context target task",
        description="pending",
        due_at=datetime.utcnow() + timedelta(hours=12),
    )
    session.add(task)
    session.commit()
    task_id = task.id
    session.close()

    proposed = client.post(
        "/agent/chat",
        json={"message": "这个任务处理完成"},
        headers=student_headers,
    )
    assert proposed.status_code == 200
    data = proposed.json()
    assert data["confirmation_required"] is True
    assert data["pending_action"]["name"] == "update_follow_up_task"
    assert data["pending_action"]["proposed_payload"]["task_id"] == task_id


def test_agent_chat_supports_task_id_phrase_without_hash(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    session = test_env["SessionLocal"]()
    task = FollowUpTask(
        resource_id=1,
        assigned_user_id=3,
        task_type="maintenance",
        status="open",
        title="Task id phrase target",
        description="pending",
        due_at=datetime.utcnow() + timedelta(hours=12),
    )
    session.add(task)
    session.commit()
    task_id = task.id
    session.close()

    proposed = client.post(
        "/agent/chat",
        json={"message": f"请把{task_id}号任务开始处理"},
        headers=student_headers,
    )
    assert proposed.status_code == 200
    data = proposed.json()
    assert data["confirmation_required"] is True
    assert data["pending_action"]["name"] == "update_follow_up_task"
    assert data["pending_action"]["proposed_payload"]["task_id"] == task_id
    assert data["pending_action"]["proposed_payload"]["status"] == "in_progress"


def test_follow_up_task_update_returns_audit_fields(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    session = test_env["SessionLocal"]()
    task = FollowUpTask(
        resource_id=1,
        assigned_user_id=3,
        task_type="accountability",
        status="open",
        title="Audit fields task",
        description="pending",
        due_at=datetime.utcnow() + timedelta(hours=6),
    )
    session.add(task)
    session.commit()
    task_id = task.id
    session.close()

    updated = client.patch(
        f"/follow-up-tasks/{task_id}",
        json={"status": "done", "note": "闭环完成", "result": "已核对完毕", "outcome_score": 92},
        headers=student_headers,
    )
    assert updated.status_code == 200
    data = updated.json()
    assert data["status"] == "done"
    assert data["closed_at"] is not None
    assert data["updated_at"] is not None
    assert data["result"] == "已核对完毕"
    assert data["outcome_score"] == 92.0


def test_overdue_follow_up_task_is_auto_escalated_and_alerted(test_env):
    client = test_env["client"]
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    session = test_env["SessionLocal"]()
    task = FollowUpTask(
        resource_id=1,
        assigned_user_id=2,
        task_type="maintenance",
        status="open",
        title="Overdue SLA task",
        description="pending",
        due_at=datetime.utcnow() - timedelta(hours=2),
    )
    session.add(task)
    session.commit()
    task_id = task.id
    session.close()

    listed = client.get("/follow-up-tasks?status=all&assigned=all", headers=teacher_headers)
    assert listed.status_code == 200
    row = next(item for item in listed.json() if item["id"] == task_id)
    assert row["sla_status"] == "overdue"
    assert row["escalation_level"] >= 1
    assert row["escalated_at"] is not None

    alerts = client.get("/alerts", headers=teacher_headers)
    assert alerts.status_code == 200
    assert any(
        alert["type"] == "follow_up_sla_overdue" and f"task#{task_id}" in alert["message"]
        for alert in alerts.json()
    )
