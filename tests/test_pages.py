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
