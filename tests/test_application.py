from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Attendance, Department, Employee, Payroll, SalaryStructure, Tax, User
from app.payroll.service import PayrollValidationError, preview_payroll


def login(client):
    return client.post(
        "/login",
        data={"username": "admin", "password": "a-long-test-password"},
        follow_redirects=True,
    )


def test_application_starts_and_login_works(client):
    response = client.get("/login")
    assert response.status_code == 200
    response = login(client)
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_password_is_hashed_and_checked(app):
    with app.app_context():
        user = db.session.query(User).filter_by(username="admin").one()
        assert user.password_hash != "a-long-test-password"
        assert user.check_password("a-long-test-password")
        assert not user.check_password("wrong-password")


def test_employee_crud_and_duplicate_email_validation(client, app):
    login(client)
    with app.app_context():
        db.session.add(Department(department_name="Engineering"))
        db.session.commit()
        department_id = Department.query.one().department_id
    response = client.post(
        "/employees/add",
        data={
            "name": "Taylor Example",
            "email": "taylor@example.com",
            "department_id": str(department_id),
            "designation": "Analyst",
            "phone": "",
            "date_of_joining": "2026-01-01",
            "employment_status": "ACTIVE",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Taylor Example" in response.data
    response = client.post(
        "/employees/add",
        data={
            "name": "Duplicate",
            "email": "taylor@example.com",
            "department_id": str(department_id),
            "designation": "Analyst",
            "date_of_joining": "2026-01-01",
            "employment_status": "ACTIVE",
        },
    )
    assert response.status_code == 200
    assert b"already exists" in response.data


def test_non_admin_cannot_create_department(client, app):
    with app.app_context():
        user = User(username="hr", email="hr@example.test", role="HR")
        user.set_password("a-long-test-password")
        db.session.add(user)
        db.session.commit()
    client.post("/login", data={"username": "hr", "password": "a-long-test-password"})
    response = client.get("/departments/add")
    assert response.status_code == 403


def test_payroll_calculation_and_duplicate_prevention(app):
    with app.app_context():
        employee = Employee(
            name="Payroll Person", email="payroll@example.test",
            designation="Associate", date_of_joining=date(2024, 1, 1)
        )
        db.session.add(employee)
        db.session.flush()
        db.session.add(SalaryStructure(
            employee_id=employee.employee_id, basic_salary=Decimal("5000.00"),
            allowances=Decimal("500.00"), overtime_rate=Decimal("20.00"),
            effective_from=date(2025, 1, 1)
        ))
        db.session.add(Tax(
            tax_type="Withholding", tax_rate=Decimal("10.0000"),
            effective_from=date(2025, 1, 1), is_active=True
        ))
        db.session.add(Attendance(
            employee_id=employee.employee_id, attendance_date=date(2026, 3, 5),
            overtime_hours=Decimal("2.00"), attendance_status="PRESENT"
        ))
        db.session.commit()
        preview = preview_payroll(employee.employee_id, 3, 2026, Decimal("100.00"))
        assert preview["gross"] == Decimal("5640.00")
        assert preview["total_deductions"] == Decimal("564.00")
        assert preview["net"] == Decimal("5076.00")
        db.session.add(Payroll(
            employee_id=employee.employee_id, payroll_month=3, payroll_year=2026,
            basic_salary=5000, allowances=500, overtime_pay=40, bonus=100,
            gross_salary=5640, total_deductions=564, net_salary=5076,
            payment_status="PENDING"
        ))
        db.session.commit()
        try:
            preview_payroll(employee.employee_id, 3, 2026)
        except PayrollValidationError as error:
            assert "already exists" in str(error)
        else:
            raise AssertionError("duplicate payroll was not rejected")


def test_duplicate_attendance_is_rejected(app):
    with app.app_context():
        employee = Employee(
            name="Attendance Person", email="attendance@example.com",
            designation="Associate", date_of_joining=date(2024, 1, 1)
        )
        db.session.add(employee)
        db.session.flush()
        date_value = date(2026, 4, 10)
        db.session.add(Attendance(
            employee_id=employee.employee_id, attendance_date=date_value,
            attendance_status="PRESENT"
        ))
        db.session.commit()
        db.session.add(Attendance(
            employee_id=employee.employee_id, attendance_date=date_value,
            attendance_status="ABSENT"
        ))
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        else:
            raise AssertionError("duplicate attendance was not rejected")


def test_employee_can_only_view_own_profile(client, app):
    with app.app_context():
        own = Employee(
            name="Own Employee", email="own@example.com",
            designation="Associate", date_of_joining=date(2024, 1, 1)
        )
        other = Employee(
            name="Other Employee", email="other@example.com",
            designation="Associate", date_of_joining=date(2024, 1, 1)
        )
        user = User(username="employee", email="employee@example.com", role="EMPLOYEE")
        user.set_password("a-long-test-password")
        db.session.add_all([own, other, user])
        db.session.flush()
        own.user_id = user.id
        own_id, other_id = own.employee_id, other.employee_id
        db.session.commit()
    client.post("/login", data={"username": "employee", "password": "a-long-test-password"})
    assert client.get(f"/employees/{own_id}").status_code == 200
    assert client.get(f"/employees/{other_id}").status_code == 403


def test_payroll_workflow_and_salary_slip(client, app):
    with app.app_context():
        employee = Employee(
            name="Payroll Flow", email="flow@example.com",
            designation="Associate", date_of_joining=date(2024, 1, 1)
        )
        db.session.add(employee)
        db.session.flush()
        employee_id = employee.employee_id
        db.session.add(SalaryStructure(
            employee_id=employee_id, basic_salary=Decimal("4000.00"),
            allowances=Decimal("500.00"), overtime_rate=Decimal("10.00"),
            effective_from=date(2025, 1, 1)
        ))
        db.session.add(Tax(
            tax_type="Income withholding", tax_rate=Decimal("5.0000"),
            effective_from=date(2025, 1, 1)
        ))
        db.session.commit()
    login(client)
    preview = client.post("/payroll/generate", data={
        "employee_id": str(employee_id), "payroll_month": "4",
        "payroll_year": "2026", "bonus": "0",
    })
    assert preview.status_code == 200
    assert b"Create pending payroll" in preview.data
    created = client.post("/payroll/confirm", data={
        "employee_id": str(employee_id), "month": "4", "year": "2026", "bonus": "0",
    }, follow_redirects=True)
    assert created.status_code == 200
    assert b"PENDING" in created.data
    with app.app_context():
        payroll_id = Payroll.query.one().payroll_id
    approved = client.post(f"/payroll/{payroll_id}/approve", follow_redirects=True)
    assert b"APPROVED" in approved.data
    paid = client.post(f"/payroll/{payroll_id}/mark-paid", follow_redirects=True)
    assert b"PAID" in paid.data
    slip = client.get(f"/payroll/{payroll_id}/slip.pdf")
    assert slip.status_code == 200
    assert slip.mimetype == "application/pdf"
    blocked = client.post(f"/payroll/{payroll_id}/approve", follow_redirects=True)
    assert b"Only pending payroll can be approved" in blocked.data
    with app.app_context():
        assert db.session.get(Payroll, payroll_id).payment_status == "PAID"


def test_user_admin_workflow_links_employee(client, app):
    login(client)
    with app.app_context():
        employee = Employee(
            name="Linked User", email="linked@example.com",
            designation="Associate", date_of_joining=date(2024, 1, 1)
        )
        db.session.add(employee)
        db.session.commit()
        employee_id = employee.employee_id
    response = client.post("/users/add", data={
        "username": "linked-user", "email": "linked-user@example.com",
        "password": "a-long-test-password", "role": "EMPLOYEE",
        "employee_id": str(employee_id), "is_active": "y",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"linked-user" in response.data
    with app.app_context():
        employee = db.session.get(Employee, employee_id)
        assert employee.user is not None
        assert employee.user.role == "EMPLOYEE"


def test_authenticated_module_pages_render(client):
    login(client)
    for path in (
        "/dashboard", "/employees/", "/employees/add", "/departments/",
        "/departments/add", "/attendance/", "/attendance/add",
        "/attendance/reports", "/payroll/", "/payroll/generate",
        "/taxes/", "/taxes/add", "/reports/", "/users/", "/users/add",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
