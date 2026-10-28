import argparse
import getpass
import os
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import (
    Attendance,
    AuditLog,
    Department,
    Employee,
    Payroll,
    PayrollTax,
    SalaryStructure,
    Tax,
    User,
)
from app.payroll.service import PayrollValidationError, create_payroll, preview_payroll


DEPARTMENTS = (
    "Information Technology",
    "Human Resources",
    "Finance",
    "Marketing",
    "Operations",
)

EMPLOYEES = (
    ("Aarav Sharma", "aarav.sharma@example.test", "Information Technology", "Software Developer", "9000000001", 40000, 8000, 250),
    ("Priya Verma", "priya.verma@example.test", "Human Resources", "HR Executive", "9000000002", 32000, 5000, 180),
    ("Rahul Singh", "rahul.singh@example.test", "Finance", "Accountant", "9000000003", 35000, 6000, 200),
    ("Ananya Gupta", "ananya.gupta@example.test", "Marketing", "Marketing Executive", "9000000004", 30000, 5000, 170),
    ("Rohan Mishra", "rohan.mishra@example.test", "Operations", "Operations Analyst", "9000000005", 28000, 4000, 150),
    ("Meera Iyer", "meera.iyer@example.test", "Information Technology", "QA Engineer", "9000000006", 36000, 5500, 190),
    ("Kabir Patel", "kabir.patel@example.test", "Human Resources", "Recruiter", "9000000007", 31000, 4500, 160),
    ("Ishita Nair", "ishita.nair@example.test", "Finance", "Financial Analyst", "9000000008", 42000, 7000, 220),
    ("Arjun Rao", "arjun.rao@example.test", "Marketing", "Content Strategist", "9000000009", 33000, 5000, 175),
    ("Kavya Das", "kavya.das@example.test", "Operations", "Team Coordinator", "9000000010", 29000, 4000, 150),
    ("Dev Malhotra", "dev.malhotra@example.test", "Information Technology", "Systems Engineer", "9000000011", 45000, 7500, 240),
    ("Sana Khan", "sana.khan@example.test", "Human Resources", "People Operations Specialist", "9000000012", 34000, 5000, 180),
    ("Vikram Joshi", "vikram.joshi@example.test", "Finance", "Payroll Analyst", "9000000013", 38000, 6000, 200),
    ("Nisha Roy", "nisha.roy@example.test", "Marketing", "Campaign Manager", "9000000014", 47000, 8000, 250),
    ("Aditya Menon", "aditya.menon@example.test", "Operations", "Operations Manager", "9000000015", 52000, 9000, 275),
)

DEMO_USERS = (
    ("admin", "admin.demo@example.test", "ADMIN", None),
    ("hr_manager", "hr.demo@example.test", "HR", None),
    ("payroll_officer", "payroll.demo@example.test", "PAYROLL_OFFICER", None),
    ("employee_demo", "employee.demo@example.test", "EMPLOYEE", "aarav.sharma@example.test"),
)

DEMO_TAXES = (
    ("Demo Percentage Deduction A", Decimal("5.0000"), None),
    ("Demo Percentage Deduction B", Decimal("2.0000"), None),
    ("Demo Fixed Deduction", None, Decimal("500.00")),
    ("Demo Insurance Deduction", Decimal("1.0000"), None),
)


def ensure_schema_is_migrated():
    inspector = inspect(db.engine)
    missing = set(db.metadata.tables) - set(inspector.get_table_names())
    if missing:
        raise RuntimeError(
            "Database schema is missing tables: "
            + ", ".join(sorted(missing))
            + ". Run `flask --app run.py db upgrade` first."
        )
    if "alembic_version" not in inspector.get_table_names():
        raise RuntimeError(
            "Migration state was not found. Run `flask --app run.py db upgrade` first."
        )
    migration_config = AlembicConfig()
    migration_config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "migrations"),
    )
    expected_heads = set(ScriptDirectory.from_config(migration_config).get_heads())
    with db.engine.connect() as connection:
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
    if current_heads != expected_heads:
        raise RuntimeError(
            "Database migration is not current. Run `flask --app run.py db upgrade` first."
        )


def add_demo_departments():
    records = {}
    inserted = 0
    for name in DEPARTMENTS:
        record = Department.query.filter_by(department_name=name).one_or_none()
        if record is None:
            record = Department(department_name=name)
            db.session.add(record)
            inserted += 1
        records[name] = record
    db.session.flush()
    return records, inserted


def add_demo_employees(departments, today):
    employees = {}
    inserted = 0
    for index, item in enumerate(EMPLOYEES):
        name, email, department, designation, phone, *_ = item
        record = Employee.query.filter_by(email=email).one_or_none()
        if record is None:
            record = Employee(
                name=name,
                email=email,
                department_id=departments[department].department_id,
                designation=designation,
                phone=phone,
                date_of_joining=date(today.year - 3 + index % 3, 1 + index % 12, 1),
                employment_status="ACTIVE",
            )
            db.session.add(record)
            inserted += 1
        employees[email] = record
    db.session.flush()
    return employees, inserted


def add_demo_salary_structures(employees, today):
    inserted = 0
    current_start = date(today.year - 1, 1, 1)
    previous_start = date(today.year - 2, 1, 1)
    previous_end = current_start - timedelta(days=1)
    for item in EMPLOYEES:
        email, basic, allowances, overtime_rate = item[1], item[5], item[6], item[7]
        employee = employees[email]
        if SalaryStructure.query.filter_by(employee_id=employee.employee_id).first():
            continue
        db.session.add_all(
            [
                SalaryStructure(
                    employee_id=employee.employee_id,
                    basic_salary=Decimal(basic) * Decimal("0.90"),
                    allowances=Decimal(allowances) * Decimal("0.90"),
                    overtime_rate=Decimal(overtime_rate),
                    effective_from=previous_start,
                    effective_to=previous_end,
                ),
                SalaryStructure(
                    employee_id=employee.employee_id,
                    basic_salary=Decimal(basic),
                    allowances=Decimal(allowances),
                    overtime_rate=Decimal(overtime_rate),
                    effective_from=current_start,
                ),
            ]
        )
        inserted += 2
    db.session.flush()
    return inserted


def add_demo_attendance(employees, today):
    inserted = 0
    start = today - timedelta(days=27)
    status_cycle = (
        ("PRESENT", False),
        ("PRESENT", False),
        ("PRESENT", False),
        ("HALF_DAY", False),
        ("ABSENT", False),
        ("LEAVE", True),
        ("UNPAID_LEAVE", False),
    )
    for employee_index, item in enumerate(EMPLOYEES):
        employee = employees[item[1]]
        day = start
        while day <= today:
            if day.weekday() < 5 and not Attendance.query.filter_by(
                employee_id=employee.employee_id, attendance_date=day
            ).first():
                status, paid_leave = status_cycle[(employee_index + day.day) % len(status_cycle)]
                if status == "PRESENT":
                    check_in, check_out, hours, overtime = (
                        datetime.strptime("09:00", "%H:%M").time(),
                        datetime.strptime("18:00", "%H:%M").time(),
                        Decimal("8.00"),
                        Decimal("1.00") if (employee_index + day.day) % 5 == 0 else Decimal("0.00"),
                    )
                elif status == "HALF_DAY":
                    check_in, check_out, hours, overtime = (
                        datetime.strptime("09:00", "%H:%M").time(),
                        datetime.strptime("13:00", "%H:%M").time(),
                        Decimal("4.00"),
                        Decimal("0.00"),
                    )
                else:
                    check_in = check_out = None
                    hours = overtime = Decimal("0.00")
                db.session.add(
                    Attendance(
                        employee_id=employee.employee_id,
                        attendance_date=day,
                        check_in=check_in,
                        check_out=check_out,
                        working_hours=hours,
                        attendance_status=status,
                        paid_leave=paid_leave,
                        overtime_hours=overtime,
                        remarks="Seeded demonstration attendance",
                    )
                )
                inserted += 1
            day += timedelta(days=1)
    db.session.flush()
    return inserted


def add_demo_taxes(today):
    inserted = 0
    for name, rate, fixed in DEMO_TAXES:
        record = Tax.query.filter_by(tax_type=name).first()
        if record is None:
            db.session.add(
                Tax(
                    tax_type=name,
                    tax_rate=rate,
                    fixed_amount=fixed,
                    effective_from=date(today.year - 2, 1, 1),
                    is_active=True,
                    description="Illustrative development-only demo deduction; not statutory advice.",
                )
            )
            inserted += 1
    db.session.flush()
    return inserted


def add_demo_users(employees, password):
    inserted = 0
    for username, email, role, employee_email in DEMO_USERS:
        user = User.query.filter(
            db.or_(User.username == username, User.email == email)
        ).first()
        if user is not None:
            continue
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        if employee_email:
            employee = employees[employee_email]
            if employee.user_id is None:
                employee.user_id = user.id
            else:
                raise RuntimeError(
                    "The demo employee is already linked to another user; "
                    "not changing the existing relationship."
                )
        inserted += 1
    db.session.flush()
    return inserted


def period_status(period_index, employee_index):
    if period_index == 0:
        if employee_index < 2:
            return "PENDING"
        if employee_index < 5:
            return "APPROVED"
    return "PAID"


def add_demo_payroll(employees, admin, today):
    inserted = 0
    periods = [(today.month, today.year)]
    previous_month = date(today.year, today.month, 1) - timedelta(days=1)
    periods.append((previous_month.month, previous_month.year))
    for period_index, (month, year) in enumerate(periods):
        for employee_index, item in enumerate(EMPLOYEES):
            employee = employees[item[1]]
            existing = Payroll.query.filter_by(
                employee_id=employee.employee_id,
                payroll_month=month,
                payroll_year=year,
            ).first()
            if existing:
                continue
            preview = preview_payroll(employee.employee_id, month, year, Decimal("1000.00"))
            payroll = create_payroll(preview, admin.id)
            status = period_status(period_index, employee_index)
            if status != "PENDING":
                payroll.payment_status = status
                if status == "PAID":
                    payroll.payment_date = date(year, month, monthrange(year, month)[1])
                db.session.add(
                    AuditLog(
                        user_id=admin.id,
                        action="DEMO_PAYROLL_STATUS",
                        entity_type="Payroll",
                        entity_id=str(payroll.payroll_id),
                        details=f"Seeded demonstration payroll status: {status}",
                    )
                )
                db.session.commit()
            inserted += 1
    return inserted


def seed_demo_data(password, today=None):
    today = today or date.today()
    if len(password) < 12:
        raise ValueError("Demo account password must contain at least 12 characters.")
    if not db.session.execute(db.text("SELECT 1")).scalar_one():
        raise RuntimeError("Database connectivity check failed.")
    ensure_schema_is_migrated()

    counts = {}
    departments, counts["departments"] = add_demo_departments()
    employees, counts["employees"] = add_demo_employees(departments, today)
    counts["salary structures"] = add_demo_salary_structures(employees, today)
    counts["attendance records"] = add_demo_attendance(employees, today)
    counts["demo deduction rules"] = add_demo_taxes(today)
    db.session.commit()

    admin = User.query.filter_by(username="admin").first()
    if admin is None:
        admin = User(
            username="admin",
            email="admin.demo@example.test",
            role="ADMIN",
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.flush()
        counts["demo users"] = 1
    else:
        counts["demo users"] = 0
    counts["demo users"] += add_demo_users(employees, password)
    db.session.commit()

    try:
        counts["payroll records"] = add_demo_payroll(employees, admin, today)
    except PayrollValidationError:
        db.session.rollback()
        raise

    audit_key = f"{today.year}-{today.month:02d}"
    if not AuditLog.query.filter_by(
        action="DEMO_DATA_SEEDED", entity_type="DemoData", entity_id=audit_key
    ).first():
        db.session.add(
            AuditLog(
                user_id=admin.id,
                action="DEMO_DATA_SEEDED",
                entity_type="DemoData",
                entity_id=audit_key,
                details="Development sample data was seeded.",
            )
        )
        db.session.commit()
        counts["audit records"] = 1
    else:
        counts["audit records"] = 0
    return counts


def clear_demo_data():
    demo_emails = [item[1] for item in EMPLOYEES]
    demo_employee_ids = [
        row[0]
        for row in db.session.query(Employee.employee_id)
        .filter(Employee.email.in_(demo_emails))
        .all()
    ]
    payroll_ids = [
        row[0]
        for row in db.session.query(Payroll.payroll_id)
        .filter(Payroll.employee_id.in_(demo_employee_ids))
        .all()
    ]
    demo_user_emails = {item[1] for item in DEMO_USERS}
    users = User.query.filter(User.email.in_(demo_user_emails)).all()
    user_ids = [user.id for user in users]

    counts = {}
    counts["payroll tax items"] = PayrollTax.query.filter(
        PayrollTax.payroll_id.in_(payroll_ids)
    ).delete(synchronize_session=False) if payroll_ids else 0
    counts["payroll records"] = Payroll.query.filter(
        Payroll.payroll_id.in_(payroll_ids)
    ).delete(synchronize_session=False) if payroll_ids else 0
    counts["attendance records"] = Attendance.query.filter(
        Attendance.employee_id.in_(demo_employee_ids)
    ).delete(synchronize_session=False) if demo_employee_ids else 0
    counts["salary structures"] = SalaryStructure.query.filter(
        SalaryStructure.employee_id.in_(demo_employee_ids)
    ).delete(synchronize_session=False) if demo_employee_ids else 0
    counts["audit records"] = AuditLog.query.filter(
        db.or_(
            AuditLog.user_id.in_(user_ids) if user_ids else db.false(),
            db.and_(
                AuditLog.entity_type == "Employee",
                AuditLog.entity_id.in_([str(employee_id) for employee_id in demo_employee_ids])
                if demo_employee_ids else db.false(),
            ),
            db.and_(
                AuditLog.entity_type == "Payroll",
                AuditLog.entity_id.in_([str(payroll_id) for payroll_id in payroll_ids])
                if payroll_ids else db.false(),
            ),
            db.and_(AuditLog.entity_type == "DemoData", AuditLog.action == "DEMO_DATA_SEEDED"),
        )
    ).delete(synchronize_session=False)

    Employee.query.filter(Employee.employee_id.in_(demo_employee_ids)).update(
        {Employee.user_id: None}, synchronize_session=False
    ) if demo_employee_ids else None
    counts["demo users"] = User.query.filter(User.email.in_(demo_user_emails)).delete(
        synchronize_session=False
    )
    counts["employees"] = Employee.query.filter(Employee.employee_id.in_(demo_employee_ids)).delete(
        synchronize_session=False
    ) if demo_employee_ids else 0
    demo_tax_names = [item[0] for item in DEMO_TAXES]
    unused_tax_ids = [
        row[0]
        for row in db.session.query(Tax.tax_id)
        .filter(Tax.tax_type.in_(demo_tax_names))
        .all()
        if not PayrollTax.query.filter_by(tax_id=row[0]).first()
    ]
    counts["demo deduction rules"] = Tax.query.filter(
        Tax.tax_id.in_(unused_tax_ids)
    ).delete(synchronize_session=False) if unused_tax_ids else 0
    counts["departments"] = Department.query.filter(
        Department.department_name.in_(DEPARTMENTS),
        ~Department.employees.any(),
    ).delete(synchronize_session=False)
    db.session.commit()
    return counts


def validate_demo_target(app, allow_sqlite=False):
    if app.config["APP_ENV"] != "development":
        raise RuntimeError("Demo data can only be seeded when APP_ENV=development.")
    if not app.config["DEMO_SEED_ENABLED"]:
        raise RuntimeError("Set DEMO_SEED_ENABLED=true in .env before seeding.")
    backend = db.engine.url.get_backend_name()
    if backend == "sqlite":
        if not allow_sqlite:
            raise RuntimeError(
                "SQLite seeding requires the explicit --allow-sqlite option."
            )
        database_path = db.engine.url.database
        instance_path = Path(app.instance_path).resolve()
        if not database_path or database_path == ":memory:":
            raise RuntimeError("SQLite demo seeding requires a file-backed database.")
        resolved_path = Path(database_path).resolve()
        try:
            resolved_path.relative_to(instance_path)
        except ValueError as error:
            raise RuntimeError(
                "SQLite demo seeding is restricted to a file inside the app instance directory."
            ) from error
        return
    if backend != "mysql":
        raise RuntimeError(
            "Demo seed supports only MySQL `payroll_db` or explicitly allowed "
            "file-backed development SQLite. No records were changed."
        )
    if db.engine.url.database != "payroll_db":
        raise RuntimeError(
            "Demo seed is restricted to the MySQL database `payroll_db`; "
            f"the configured database is `{db.engine.url.database}`. No records were changed."
        )
    host = db.engine.url.host
    if host not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise RuntimeError("Demo seeding is restricted to a local MySQL server.")


def main():
    parser = argparse.ArgumentParser(description="Seed connected development demo data.")
    parser.add_argument(
        "--confirm-demo-data",
        action="store_true",
        help="Required confirmation for seeding or clearing development demo data.",
    )
    parser.add_argument(
        "--clear-demo",
        action="store_true",
        help="Remove only the reserved demo identifiers created by this script.",
    )
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="Allow seeding the configured file-backed SQLite database in the app instance directory.",
    )
    args = parser.parse_args()
    if not args.confirm_demo_data:
        parser.error("pass --confirm-demo-data to confirm a development-only database")

    app = create_app()
    with app.app_context():
        validate_demo_target(app, allow_sqlite=args.allow_sqlite)
        ensure_schema_is_migrated()
        if args.clear_demo:
            confirmation = input(
                "Type CLEAR DEMO to remove records with reserved demo identifiers: "
            )
            if confirmation != "CLEAR DEMO":
                raise SystemExit("Demo cleanup cancelled.")
            print("Demo data cleanup (reserved demo identifiers only):")
            for label, count in clear_demo_data().items():
                print(f"  {label}: {count}")
            return
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception as error:
            raise SystemExit(
                f"Database connection failed for the configured DATABASE_URL: {error}"
            ) from error

        missing_users = [
            username
            for username, email, _, _ in DEMO_USERS
            if not User.query.filter(
                db.or_(User.username == username, User.email == email)
            ).first()
        ]
        admin_missing = User.query.filter_by(username="admin").first() is None
        password = os.getenv("DEMO_ACCOUNT_PASSWORD")
        if (missing_users or admin_missing) and not password:
            password = getpass.getpass(
                "Password for newly created demo accounts (minimum 12 characters): "
            )
        try:
            counts = seed_demo_data(password or "not-used-demo-password")
        except Exception:
            db.session.rollback()
            raise
        print("Demo data seeding complete (new rows only):")
        for label, count in counts.items():
            print(f"  {label}: {count}")
        print("Existing records were preserved.")
        if missing_users or admin_missing:
            print("Demo account usernames: admin, hr_manager, payroll_officer, employee_demo")
            print("The password is the password entered above or DEMO_ACCOUNT_PASSWORD.")
        else:
            print("Existing demo account passwords were not changed.")


if __name__ == "__main__":
    main()
