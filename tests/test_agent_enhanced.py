from datetime import datetime, timedelta

from tests.conftest import login_as


def test_login_returns_bearer_jwt(test_env):
    client = test_env["client"]
    response = client.post("/auth/login", json={"username": "student1", "password": "123456"})
    assert response.status_code == 200
    assert response.json()["token"].startswith("Bearer ")
    assert response.json()["token"] != "Bearer 3"


def test_agent_chat_requires_auth(test_env):
    client = test_env["client"]
    response = client.post("/agent/chat", json={"message": "你好"})
    assert response.status_code == 401


def test_agent_chat_can_confirm_and_create_borrow_application(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    proposed = client.post(
        "/agent/chat",
        json={"message": "帮我申请借用 3D Printer 1台 明天下午 2小时 项目 Alpha"},
        headers=student_headers,
    )
    assert proposed.status_code == 200
    data = proposed.json()
    assert data["confirmation_required"] is True
    assert data["pending_action"]["name"] == "submit_borrow_application"

    confirmed = client.post(
        "/agent/chat",
        json={"message": "确认", "session_id": data["session_id"]},
        headers=student_headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["executed_tools"][0]["name"] == "submit_borrow_application"

    approvals = client.get("/approvals?status=pending", headers=teacher_headers)
    assert approvals.status_code == 200
    assert len(approvals.json()) == 1
    assert approvals.json()[0]["resource_name"] == "3D Printer"


def test_agent_session_is_owner_bound(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    response = client.post("/agent/chat", json={"message": "查一下库存"}, headers=student_headers)
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    forbidden = client.get(f"/agent/sessions/{session_id}/messages", headers=teacher_headers)
    assert forbidden.status_code == 404


def test_scheduler_endpoint_returns_slots(test_env):
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
    assert response.json()["resource_id"] == 1
    assert isinstance(response.json()["optimal_slots"], list)


def test_analytics_and_qiniu_are_authenticated(test_env):
    client = test_env["client"]
    assert client.get("/analytics/overview").status_code == 401
    assert client.get("/files/qiniu-token").status_code == 401


def test_inventory_vision_endpoint_returns_diff_and_suggestions(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")

    response = client.post(
        "/files/evidence/inventory-vision",
        json={
            "resource_id": 1,
            "evidence_url": "qiniu://audit/photo-3.jpg",
            "evidence_type": "image",
            "observed_count": 2,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["resource_id"] == 1
    assert data["recognized_count"] == 2
    assert isinstance(data["suggestions"], list)


def test_enhanced_agent_route_returns_real_time_data(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    response = client.post(
        "/enhanced-agent/ask",
        json={"question": "查一下 3D Printer 的库存"},
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "real_time_data" in data
    assert "low_inventory_resources" in data["real_time_data"]


def test_enhanced_analytics_admin_only_and_schema(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    student_headers, _ = login_as(client, "student1", "123456")

    forbidden = client.get("/enhanced-analytics/comprehensive", headers=student_headers)
    assert forbidden.status_code == 403

    response = client.get("/enhanced-analytics/comprehensive", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "fairness_metrics" in data
    assert "overdue_returns" in data
    assert "prime_time_monopolies" in data
    assert "project_usage_variance" in data
    assert "anomaly_scores" in data


def test_enhanced_demand_prediction_schema(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")
    response = client.get("/enhanced-analytics/demand-prediction/1?days_ahead=5", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["resource_id"] == 1
    assert data["days_ahead"] == 5
    assert data["prediction_method"]
    assert len(data["predictions"]) == 5
