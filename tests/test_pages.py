def test_dashboard_html_contains_student_application_flow():
    html = open("app/static/dashboard-main.html", "r", encoding="utf-8").read()
    assert "student-apply-section" in html
    assert "borrow-records-section" in html
    assert "const roleCanApply=r=>r==='student'||r==='teacher';" in html


def test_dashboard_html_contains_teacher_approval_flow():
    html = open("app/static/dashboard-main.html", "r", encoding="utf-8").read()
    assert "approval-center-section" in html
    assert "const roleCanApprove=r=>r==='teacher'||r==='admin';" in html
    assert "审批通过，库存已更新" in html


def test_dashboard_and_login_html_contains_admin_inventory_flow():
    dashboard_html = open("app/static/dashboard-main.html", "r", encoding="utf-8").read()
    login_html = open("app/static/login.html", "r", encoding="utf-8").read()
    assert "inventory-adjustment-section" in dashboard_html
    assert "resource-management-section" in dashboard_html
    assert "const roleCanManageInventory=r=>r==='admin';" in dashboard_html
    assert "公开注册只创建学生账号" in login_html


def test_dashboard_resource_table_contains_subtype_and_admin_actions():
    html = open("app/static/dashboard-main.html", "r", encoding="utf-8").read()
    assert "<th>子类</th>" in html
    assert "resource-recovery-section" in html
    assert "删除当前资源" in html
    assert "撤回上次删除" in html
    assert "show-archived-resources" in html
    assert "deleteResource(" in html
    assert "restoreResource(" in html
    assert "undoLastDelete(" in html
    assert "fillResourceForm(" in html


def test_dashboard_inventory_adjustment_polling_does_not_interrupt_editing():
    html = open("app/static/dashboard-main.html", "r", encoding="utf-8").read()
    assert "inventoryFormDirty" in html
    assert "if(inventoryFormDirty)return;" in html
    assert "const prevSelected=adjustSelect.value" in html


def test_dashboard_alerts_support_ack_and_resolve_actions():
    html = open("app/static/dashboard-main.html", "r", encoding="utf-8").read()
    assert "roleCanManageAlerts" in html
    assert "acknowledgeAlert(" in html
    assert "resolveAlert(" in html


def test_dashboard_hides_readiness_panel_in_normal_mode():
    html = open("app/static/dashboard-main.html", "r", encoding="utf-8").read()
    assert 'id="readiness-section"' not in html
    assert "runReadinessCheck()" not in html
    assert 'id="readiness-probe-llm"' not in html
    assert "loadReadiness(" not in html


def test_dashboard_agent_panel_shows_analysis_steps_and_confirm_controls():
    html = open("app/static/dashboard-main.html", "r", encoding="utf-8").read()
    assert 'id="agent-meta-box"' in html
    assert "renderAgentMeta(" in html
    assert "confirmPendingActionQuick()" in html
    assert "cancelPendingActionQuick()" in html
