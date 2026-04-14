from app.models import Alert
from tests.conftest import login_as


def test_teacher_can_acknowledge_and_resolve_alert(test_env):
    client = test_env["client"]
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    session = test_env["SessionLocal"]()

    alert = Alert(level="warn", type="possible_waste", message="high consume event")
    session.add(alert)
    session.commit()
    alert_id = alert.id
    session.close()

    acknowledged = client.post(
        f"/alerts/{alert_id}/acknowledge",
        json={"note": "checked by teacher"},
        headers=teacher_headers,
    )
    assert acknowledged.status_code == 200
    ack_data = acknowledged.json()
    assert ack_data["status"] == "acknowledged"
    assert ack_data["resolution_note"] == "checked by teacher"

    listed = client.get("/alerts", headers=teacher_headers)
    assert listed.status_code == 200
    assert any(item["id"] == alert_id for item in listed.json())

    resolved = client.post(
        f"/alerts/{alert_id}/resolve",
        json={"note": "already handled"},
        headers=teacher_headers,
    )
    assert resolved.status_code == 200

    listed_default = client.get("/alerts", headers=teacher_headers)
    assert listed_default.status_code == 200
    assert all(item["id"] != alert_id for item in listed_default.json())

    listed_all = client.get("/alerts?include_resolved=true", headers=teacher_headers)
    assert listed_all.status_code == 200
    restored = next(item for item in listed_all.json() if item["id"] == alert_id)
    assert restored["status"] == "resolved"
    assert restored["resolution_note"] == "already handled"


def test_student_cannot_acknowledge_or_resolve_alert(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    session = test_env["SessionLocal"]()

    alert = Alert(level="warn", type="low_inventory", message="low stock")
    session.add(alert)
    session.commit()
    alert_id = alert.id
    session.close()

    ack = client.post(
        f"/alerts/{alert_id}/acknowledge",
        json={"note": "try ack"},
        headers=student_headers,
    )
    assert ack.status_code == 403

    resolve = client.post(
        f"/alerts/{alert_id}/resolve",
        json={"note": "try resolve"},
        headers=student_headers,
    )
    assert resolve.status_code == 403
