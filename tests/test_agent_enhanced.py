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


def test_agent_chat_recognizes_borrow_synonym_expression(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    proposed = client.post(
        "/agent/chat",
        json={"message": "请帮我预约3D打印机 明天下午 两小时 项目 Beta"},
        headers=student_headers,
    )
    assert proposed.status_code == 200
    data = proposed.json()
    assert data["confirmation_required"] is True
    assert data["pending_action"]["name"] == "submit_borrow_application"


def test_agent_session_is_owner_bound(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    response = client.post("/agent/chat", json={"message": "查一下库存"}, headers=student_headers)
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    forbidden = client.get(f"/agent/sessions/{session_id}/messages", headers=teacher_headers)
    assert forbidden.status_code == 404


def test_teacher_can_approve_with_context_reference_without_explicit_id(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    teacher_headers, _ = login_as(client, "teacher1", "123456")

    created = client.post(
        "/transactions",
        json={
            "resource_id": 1,
            "action": "borrow",
            "quantity": 1,
            "purpose": "course project",
            "note": "Need for context approve test",
            "borrow_time": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            "expected_return_time": (datetime.utcnow() + timedelta(days=1, hours=2)).isoformat(),
        },
        headers=student_headers,
    )
    assert created.status_code == 200

    proposed = client.post(
        "/agent/chat",
        json={"message": "请通过这个审批"},
        headers=teacher_headers,
    )
    assert proposed.status_code == 200
    data = proposed.json()
    assert data["confirmation_required"] is True
    assert data["pending_action"]["name"] == "approve_task"

    confirmed = client.post(
        "/agent/chat",
        json={"message": "确认", "session_id": data["session_id"]},
        headers=teacher_headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["executed_tools"][0]["name"] == "approve_task"


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


def test_agent_chat_schedule_reply_is_direct_and_actionable(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    response = client.post(
        "/agent/chat",
        json={"message": "我明天下午想用3D打印机，有空档吗"},
        headers=student_headers,
    )
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "3D Printer" in reply
    assert "有空档" in reply or "当前没有完全空档" in reply
    assert "建议" in reply
    assert "时段如下" in reply


def test_agent_chat_returns_analysis_steps(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    response = client.post(
        "/agent/chat",
        json={"message": "我明天下午想用3D打印机，有空档吗"},
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["analysis_steps"], list)
    assert len(data["analysis_steps"]) >= 2
    assert any("感知输入" in step for step in data["analysis_steps"])
    assert any("推理规划" in step for step in data["analysis_steps"])


def test_agent_chat_understands_day_after_tomorrow_schedule(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    expected_day = (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d")
    response = client.post(
        "/agent/chat",
        json={"message": "我后天下午想用3D打印机，有空档吗"},
        headers=student_headers,
    )
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert expected_day in reply


def test_agent_chat_understands_next_week_time_expression(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    now = datetime.utcnow()
    start_of_current_week = now.date() - timedelta(days=now.weekday())
    expected_date = (start_of_current_week + timedelta(days=7 + 2)).strftime("%Y-%m-%d")  # 下周三

    response = client.post(
        "/agent/chat",
        json={"message": "我下周三下午3点半想用3D打印机，有空档吗"},
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert any(expected_date in step and "15:30" in step for step in data["analysis_steps"])


def test_agent_chat_accepts_request_level_llm_options(test_env, monkeypatch):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    called = {}

    def fake_llm_call(messages, runtime_config):
        called["base_url"] = runtime_config.base_url
        called["api_key"] = runtime_config.api_key
        called["model"] = runtime_config.model
        return "这是来自大模型的回答"

    monkeypatch.setattr("app.services.llm_service._call_openai_compatible", fake_llm_call)

    response = client.post(
        "/agent/chat",
        json={
            "message": "查一下 3D Printer 的库存",
            "llm_options": {
                "enabled": True,
                "base_url": "https://example.com/v1",
                "api_key": "test-key",
                "model": "test-model",
                "timeout": 20,
            },
        },
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["used_model"] is True
    assert data["reply"] == "这是来自大模型的回答"
    assert called == {
        "base_url": "https://example.com/v1",
        "api_key": "test-key",
        "model": "test-model",
    }


def test_agent_chat_provides_governance_suggestions_for_topic_d(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    response = client.post(
        "/agent/chat",
        json={"message": "怎么优化资源利用率并减少耗材浪费和工具丢失？"},
        headers=student_headers,
    )
    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "建议优先做这 3 件事" in reply
    assert "均衡占用" in reply
    assert "控制浪费" in reply
    assert "降低丢失风险" in reply


def test_agent_chat_can_convert_governance_suggestion_to_replenish_approval(test_env):
    client = test_env["client"]
    teacher_headers, _ = login_as(client, "teacher1", "123456")
    admin_headers, _ = login_as(client, "admin", "admin123")

    proposed = client.post(
        "/agent/chat",
        json={"message": "按建议补货，帮我生成补货审批单"},
        headers=teacher_headers,
    )
    assert proposed.status_code == 200
    proposed_data = proposed.json()
    assert proposed_data["confirmation_required"] is True
    assert proposed_data["pending_action"]["name"] == "create_replenish_approval"

    confirmed = client.post(
        "/agent/chat",
        json={"message": "确认", "session_id": proposed_data["session_id"]},
        headers=teacher_headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["executed_tools"][0]["name"] == "create_replenish_approval"

    approvals = client.get("/approvals?status=pending", headers=admin_headers)
    assert approvals.status_code == 200
    assert any(item["action"] == "replenish" for item in approvals.json())


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


def test_inventory_vision_returns_multimodal_fusion_fields(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")

    response = client.post(
        "/files/evidence/inventory-vision",
        json={
            "resource_id": 1,
            "evidence_url": "qiniu://audit/photo-count-4.jpg",
            "evidence_type": "image",
            "ocr_text": "盘点记录：数量 3 台，标签编号 2026。",
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "recognition_confidence" in data
    assert 0.0 <= data["recognition_confidence"] <= 1.0
    assert "recognized_sources" in data
    assert isinstance(data["recognized_sources"], list)
    assert "extracted_candidates" in data
    assert isinstance(data["extracted_candidates"], list)
    assert "disagreement_index" in data
    assert data["disagreement_index"] >= 0.0


def test_inventory_vision_observed_count_as_multimodal_signal(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")

    response = client.post(
        "/files/evidence/inventory-vision",
        json={
            "resource_id": 1,
            "evidence_url": "qiniu://audit/photo-9.jpg",
            "evidence_type": "image",
            "observed_count": 2,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "manual_observed_count" in data["recognized_sources"]


def test_inventory_vision_missing_evidence_creates_backfill_task(test_env):
    client = test_env["client"]
    admin_headers, _ = login_as(client, "admin", "admin123")

    response = client.post(
        "/files/evidence/inventory-vision",
        json={
            "resource_id": 1,
            "evidence_url": "",
            "evidence_type": "",
            "observed_count": 2,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert any("自动创建补证任务" in text for text in data["suggestions"])

    tasks = client.get("/follow-up-tasks?status=all&assigned=all", headers=admin_headers)
    assert tasks.status_code == 200
    assert any(item["task_type"] == "evidence_backfill" and "盘点" in item["title"] for item in tasks.json())


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
    assert isinstance(data["analysis_steps"], list)
    assert len(data["analysis_steps"]) >= 2


def test_enhanced_agent_returns_multi_agent_trace(test_env):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")
    response = client.post(
        "/enhanced-agent/ask",
        json={"question": "请结合治理与证据情况给我建议"},
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "multi_agent_trace" in data
    assert isinstance(data["multi_agent_trace"], list)
    assert len(data["multi_agent_trace"]) >= 3
    agent_names = {item["agent"] for item in data["multi_agent_trace"]}
    assert {"scheduler_agent", "governance_agent", "evidence_agent"}.issubset(agent_names)
    assert data["orchestration_summary"]


def test_enhanced_agent_accepts_request_level_llm_options(test_env, monkeypatch):
    client = test_env["client"]
    student_headers, _ = login_as(client, "student1", "123456")

    def fake_llm_call(messages, runtime_config):
        return "增强路由大模型回复"

    monkeypatch.setattr("app.services.llm_service._call_openai_compatible", fake_llm_call)

    response = client.post(
        "/enhanced-agent/ask",
        json={
            "question": "查一下 3D Printer 的库存",
            "llm_options": {
                "enabled": True,
                "base_url": "https://example.com/v1",
                "api_key": "test-key",
                "model": "test-model",
                "timeout": 20,
            },
        },
        headers=student_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "增强路由大模型回复"
    assert data["success"] is True


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
