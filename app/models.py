from datetime import date, datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(30), nullable=False, default="EMPLOYEE", index=True
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    employee = db.relationship("Employee", back_populates="user", uselist=False)

    def set_password(self, password):
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters.")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Department(db.Model):
    department_id = db.Column(db.Integer, primary_key=True)
    department_name = db.Column(db.String(120), unique=True, nullable=False)
    employees = db.relationship("Employee", back_populates="department")


class Employee(db.Model):
    employee_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    department_id = db.Column(
        db.Integer, db.ForeignKey("department.department_id", ondelete="RESTRICT")
    )
    designation = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40))
    date_of_joining = db.Column(db.Date, nullable=False, default=date.today)
    employment_status = db.Column(
        db.String(20), nullable=False, default="ACTIVE", index=True
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True)
    department = db.relationship("Department", back_populates="employees")
    user = db.relationship("User", back_populates="employee")
    attendance_records = db.relationship("Attendance", back_populates="employee")
    salary_structures = db.relationship(
        "SalaryStructure", back_populates="employee", order_by="SalaryStructure.effective_from"
    )
    payroll_records = db.relationship("Payroll", back_populates="employee")


class Attendance(db.Model):
    attendance_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employee.employee_id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    attendance_date = db.Column(db.Date, nullable=False, index=True)
    check_in = db.Column(db.Time)
    check_out = db.Column(db.Time)
    working_hours = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    attendance_status = db.Column(db.String(20), nullable=False, default="PRESENT")
    paid_leave = db.Column(db.Boolean, nullable=False, default=False)
    overtime_hours = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    remarks = db.Column(db.String(500))
    employee = db.relationship("Employee", back_populates="attendance_records")
    __table_args__ = (
        db.UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_day"),
    )


class SalaryStructure(db.Model):
    salary_structure_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employee.employee_id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    basic_salary = db.Column(db.Numeric(12, 2), nullable=False)
    allowances = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    overtime_rate = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    employee = db.relationship("Employee", back_populates="salary_structures")
    __table_args__ = (
        db.CheckConstraint("basic_salary >= 0", name="ck_salary_basic_nonnegative"),
        db.CheckConstraint("allowances >= 0", name="ck_salary_allowances_nonnegative"),
        db.CheckConstraint("overtime_rate >= 0", name="ck_salary_overtime_nonnegative"),
    )


class Tax(db.Model):
    tax_id = db.Column(db.Integer, primary_key=True)
    tax_type = db.Column(db.String(120), nullable=False)
    tax_rate = db.Column(db.Numeric(7, 4))
    fixed_amount = db.Column(db.Numeric(12, 2))
    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    description = db.Column(db.String(500))
    payroll_taxes = db.relationship("PayrollTax", back_populates="tax")
    __table_args__ = (
        db.CheckConstraint(
            "(tax_rate IS NOT NULL AND fixed_amount IS NULL AND tax_rate >= 0 AND tax_rate <= 100) "
            "OR (fixed_amount IS NOT NULL AND tax_rate IS NULL AND fixed_amount >= 0)",
            name="ck_tax_one_nonnegative_method",
        ),
    )


class Payroll(db.Model):
    payroll_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer, db.ForeignKey("employee.employee_id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    payroll_month = db.Column(db.Integer, nullable=False)
    payroll_year = db.Column(db.Integer, nullable=False)
    basic_salary = db.Column(db.Numeric(12, 2), nullable=False)
    allowances = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    overtime_pay = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    bonus = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    gross_salary = db.Column(db.Numeric(12, 2), nullable=False)
    total_deductions = db.Column(db.Numeric(12, 2), nullable=False)
    net_salary = db.Column(db.Numeric(12, 2), nullable=False)
    payment_date = db.Column(db.Date)
    payment_status = db.Column(
        db.String(20), nullable=False, default="PENDING", index=True
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    employee = db.relationship("Employee", back_populates="payroll_records")
    payroll_taxes = db.relationship("PayrollTax", back_populates="payroll")
    __table_args__ = (
        db.UniqueConstraint(
            "employee_id", "payroll_month", "payroll_year", name="uq_payroll_period"
        ),
        db.CheckConstraint("payroll_month BETWEEN 1 AND 12", name="ck_payroll_month"),
        db.CheckConstraint("payroll_year BETWEEN 2000 AND 2200", name="ck_payroll_year"),
        db.CheckConstraint("gross_salary >= 0 AND net_salary >= 0", name="ck_payroll_amounts"),
    )


class PayrollTax(db.Model):
    payroll_tax_id = db.Column(db.Integer, primary_key=True)
    payroll_id = db.Column(
        db.Integer, db.ForeignKey("payroll.payroll_id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    tax_id = db.Column(
        db.Integer, db.ForeignKey("tax.tax_id", ondelete="RESTRICT"), nullable=False
    )
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False)
    tax_type_snapshot = db.Column(db.String(120), nullable=False)
    payroll = db.relationship("Payroll", back_populates="payroll_taxes")
    tax = db.relationship("Tax", back_populates="payroll_taxes")
    __table_args__ = (
        db.UniqueConstraint("payroll_id", "tax_id", name="uq_payroll_tax"),
        db.CheckConstraint("tax_amount >= 0", name="ck_payroll_tax_nonnegative"),
    )


class AuditLog(db.Model):
    audit_log_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(80))
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    user = db.relationship("User")


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None