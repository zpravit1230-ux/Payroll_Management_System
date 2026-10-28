from datetime import date, timedelta
from decimal import Decimal

from flask import abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import case, func

from app.dashboard import bp
from app.extensions import db
from app.models import Attendance, Department, Employee, Payroll


@bp.get("/dashboard")
@login_required
def index():
    today = date.today()
    month = request.args.get("month", today.month, type=int)
    year = request.args.get("year", today.year, type=int)
    if not 1 <= month <= 12 or not 2000 <= year <= 2200:
        month, year = today.month, today.year
    employee = current_user.employee if current_user.role == "EMPLOYEE" else None
    if current_user.role == "EMPLOYEE" and employee is None:
        abort(403)
    attendance_query = Attendance.query
    payroll_query = Payroll.query
    employee_query = Employee.query
    if employee:
        attendance_query = attendance_query.filter_by(employee_id=employee.employee_id)
        payroll_query = payroll_query.filter_by(employee_id=employee.employee_id)
        employee_query = employee_query.filter_by(employee_id=employee.employee_id)
    present_today = attendance_query.filter_by(
        attendance_date=today, attendance_status="PRESENT"
    ).count()
    leave_today = attendance_query.filter_by(
        attendance_date=today,
    ).filter(
        Attendance.attendance_status.in_(("LEAVE", "UNPAID_LEAVE"))
    ).count()
    payroll_totals = payroll_query.with_entities(
        func.coalesce(func.sum(Payroll.gross_salary), 0),
        func.coalesce(func.sum(Payroll.net_salary), 0),
    ).filter(Payroll.payroll_month == month, Payroll.payroll_year == year).first()
    can_see_payroll = current_user.role in ("ADMIN", "PAYROLL_OFFICER", "EMPLOYEE")
    pending_approvals = (
        payroll_query.filter_by(payment_status="PENDING").count()
        if current_user.role in ("ADMIN", "PAYROLL_OFFICER") else 0
    )
    if not can_see_payroll:
        payroll_totals = (0, 0)
    dept_rows = db.session.query(
        Department.department_name, func.count(Employee.employee_id)
    ).outerjoin(Employee).group_by(Department.department_id)
    if employee:
        dept_rows = dept_rows.filter(Department.department_id == employee.department_id)
    dept_rows = dept_rows.all()
    monthly = (
        payroll_query.with_entities(
            Payroll.payroll_month,
            func.coalesce(func.sum(Payroll.gross_salary), 0),
            func.coalesce(func.sum(Payroll.total_deductions), 0),
        ).filter(Payroll.payroll_year == year).group_by(Payroll.payroll_month).all()
        if can_see_payroll else []
    )
    attendance_trend = (
        attendance_query.with_entities(
            Attendance.attendance_date,
            func.sum(case((Attendance.attendance_status == "PRESENT", 1), else_=0)),
            func.sum(case((Attendance.attendance_status == "HALF_DAY", 1), else_=0)),
        )
        .filter(Attendance.attendance_date >= today - timedelta(days=13))
        .group_by(Attendance.attendance_date)
        .order_by(Attendance.attendance_date)
        .all()
    )
    payment_status_rows = (
        payroll_query.with_entities(Payroll.payment_status, func.count(Payroll.payroll_id))
        .filter(Payroll.payroll_month == month, Payroll.payroll_year == year)
        .group_by(Payroll.payment_status)
        .all()
        if can_see_payroll else []
    )
    return render_template(
        "dashboard.html",
        month=month,
        year=year,
        total_count=employee_query.count(),
        active_count=employee_query.filter_by(employment_status="ACTIVE").count(),
        department_count=(1 if employee and employee.department_id else Department.query.count() if not employee else 0),
        present_today=present_today,
        leave_today=leave_today,
        gross_total=payroll_totals[0] or Decimal("0"),
        net_total=payroll_totals[1] or Decimal("0"),
        pending_approvals=pending_approvals,
        department_labels=[row[0] for row in dept_rows],
        department_values=[row[1] for row in dept_rows],
        payroll_months=[row[0] for row in monthly],
        payroll_gross=[float(row[1]) for row in monthly],
        payroll_deductions=[float(row[2]) for row in monthly],
        attendance_dates=[row[0].isoformat() for row in attendance_trend],
        attendance_present=[int(row[1] or 0) for row in attendance_trend],
        attendance_half_days=[int(row[2] or 0) for row in attendance_trend],
        payment_status_labels=[row[0] for row in payment_status_rows],
        payment_status_values=[row[1] for row in payment_status_rows],
    )
