from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Attendance, Department, Employee, Payroll, PayrollTax, SalaryStructure, Tax, User
from scripts.seed_demo_data import clear_demo_data, seed_demo_data, validate_demo_target


def test_demo_seed_is_connected_and_idempotent(app):
    with app.app_context():
        db.session.execute(
            db.text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL)"
            )
        )
        db.session.execute(
            db.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "2869ebb46f6a"},
        )
        db.session.commit()

        first = seed_demo_data("test-demo-password-123", today=date(2026, 10, 23))
        second = seed_demo_data("test-demo-password-123", today=date(2026, 10, 23))

        assert first["departments"] == 5
        assert first["employees"] == 15
        assert first["salary structures"] == 30
        assert first["demo deduction rules"] == 4
        assert first["payroll records"] == 30
        assert all(count == 0 for count in second.values())
        assert Department.query.count() == 5
        assert Employee.query.count() == 15
        assert Attendance.query.count() > 100
        assert SalaryStructure.query.count() == 30
        assert Tax.query.count() == 4
        assert Payroll.query.count() == 30
        assert PayrollTax.query.count() == Payroll.query.count() * 4
        demo_employee = Employee.query.filter_by(email="aarav.sharma@example.test").one()
        assert demo_employee.user.username == "employee_demo"
        assert demo_employee.user.check_password("test-demo-password-123")
        assert all(
            payroll.net_salary
            == Decimal(payroll.gross_salary) - Decimal(payroll.total_deductions)
            for payroll in Payroll.query.all()
        )
        assert all(
            sum((Decimal(item.tax_amount) for item in payroll.payroll_taxes), Decimal("0"))
            == Decimal(payroll.total_deductions)
            for payroll in Payroll.query.all()
        )


def test_demo_seed_requires_explicit_enablement(app):
    with app.app_context():
        with pytest.raises(RuntimeError, match="DEMO_SEED_ENABLED"):
            validate_demo_target(app)
        app.config["DEMO_SEED_ENABLED"] = True
        with pytest.raises(RuntimeError, match="--allow-sqlite"):
            validate_demo_target(app)
        with pytest.raises(RuntimeError, match="file-backed"):
            validate_demo_target(app, allow_sqlite=True)


def test_demo_cleanup_removes_reserved_demo_rows_only(app):
    with app.app_context():
        db.session.execute(
            db.text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL)"
            )
        )
        db.session.execute(
            db.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "2869ebb46f6a"},
        )
        db.session.commit()
        seed_demo_data("test-demo-password-123", today=date(2026, 10, 23))

        removed = clear_demo_data()

        assert removed["payroll records"] == 30
        assert Employee.query.count() == 0
        assert Department.query.count() == 0
        assert Payroll.query.count() == 0
        assert User.query.filter_by(username="admin").one().email == "admin@example.test"


def test_seeded_reports_dashboard_and_exports_use_database_records(app, client):
    with app.app_context():
        db.session.execute(
            db.text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL)"
            )
        )
        db.session.execute(
            db.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "2869ebb46f6a"},
        )
        db.session.commit()
        seed_demo_data("test-demo-password-123", today=date.today())

    client.post(
        "/login",
        data={"username": "admin", "password": "a-long-test-password"},
        follow_redirects=True,
    )
    assert client.get("/dashboard").status_code == 200
    for report in (
        "payroll",
        "annual_payroll",
        "employees",
        "departments",
        "attendance",
        "leave",
        "tax",
        "pending_payroll",
        "paid_payroll",
        "department_payroll",
    ):
        response = client.get(f"/reports/?report={report}")
        assert response.status_code == 200, report
        assert client.get(f"/reports/export.csv?report={report}").status_code == 200
        pdf_response = client.get(f"/reports/export.pdf?report={report}")
        assert pdf_response.status_code == 200
        assert pdf_response.data.startswith(b"%PDF")
