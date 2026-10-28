from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.audit import record_action
from app.attendance import bp
from app.decorators import roles_required
from app.extensions import db
from app.forms import AttendanceForm
from app.models import Attendance, Employee


def configure_form(form):
    employees = Employee.query.order_by(Employee.name).all()
    if current_user.role == "EMPLOYEE":
        employees = [current_user.employee] if current_user.employee else []
    form.employee_id.choices = [(e.employee_id, e.name) for e in employees]


@bp.get("/")
@login_required
def list_attendance():
    query = Attendance.query.join(Employee)
    if current_user.role == "EMPLOYEE":
        if current_user.employee is None:
            abort(403)
        query = query.filter(Attendance.employee_id == current_user.employee.employee_id)
    date_filter = request.args.get("date", "")
    if date_filter:
        try:
            query = query.filter(Attendance.attendance_date == date.fromisoformat(date_filter))
        except ValueError:
            flash("Enter a valid date.", "warning")
    rows = query.order_by(Attendance.attendance_date.desc()).limit(500).all()
    return render_template("attendance/list.html", rows=rows, date_filter=date_filter)


@bp.route("/add", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN", "HR")
def add():
    form = AttendanceForm()
    configure_form(form)
    if form.validate_on_submit():
        if form.check_in.data and form.check_out.data:
            start = datetime.combine(form.attendance_date.data, form.check_in.data)
            end = datetime.combine(form.attendance_date.data, form.check_out.data)
            if end <= start:
                form.check_out.errors.append("Check-out must be later than check-in.")
            else:
                hours = Decimal(str((end - start).total_seconds() / 3600))
        elif form.check_in.data or form.check_out.data:
            hours = Decimal("0")
            form.check_out.errors.append("Provide both check-in and check-out times.")
        else:
            hours = Decimal("0")
        if not form.check_out.errors:
            try:
                row = Attendance(
                    employee_id=form.employee_id.data,
                    attendance_date=form.attendance_date.data,
                    check_in=form.check_in.data,
                    check_out=form.check_out.data,
                    working_hours=hours.quantize(Decimal("0.01")),
                    attendance_status=form.attendance_status.data,
                    paid_leave=form.paid_leave.data,
                    overtime_hours=form.overtime_hours.data,
                    remarks=form.remarks.data,
                )
                db.session.add(row)
                db.session.flush()
                record_action("ATTENDANCE_CREATED", "Attendance", row.attendance_id)
                db.session.commit()
                flash("Attendance recorded.", "success")
                return redirect(url_for("attendance.list_attendance"))
            except IntegrityError:
                db.session.rollback()
                form.attendance_date.errors.append(
                    "Attendance has already been entered for this employee and date."
                )
    return render_template("attendance/form.html", form=form, title="Record attendance")


@bp.route("/<int:attendance_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN", "HR")
def edit(attendance_id):
    row = db.session.get(Attendance, attendance_id)
    if row is None:
        abort(404)
    form = AttendanceForm(obj=row)
    configure_form(form)
    if form.validate_on_submit():
        if form.check_in.data and form.check_out.data:
            start = datetime.combine(form.attendance_date.data, form.check_in.data)
            end = datetime.combine(form.attendance_date.data, form.check_out.data)
            if end <= start:
                form.check_out.errors.append("Check-out must be later than check-in.")
        elif bool(form.check_in.data) != bool(form.check_out.data):
            form.check_out.errors.append("Provide both check-in and check-out times.")
        if not form.check_out.errors:
            row.employee_id = form.employee_id.data
            row.attendance_date = form.attendance_date.data
            row.check_in, row.check_out = form.check_in.data, form.check_out.data
            row.working_hours = (
                Decimal(str((end - start).total_seconds() / 3600)).quantize(Decimal("0.01"))
                if form.check_in.data and form.check_out.data else Decimal("0")
            )
            row.attendance_status = form.attendance_status.data
            row.paid_leave = form.paid_leave.data
            row.overtime_hours = form.overtime_hours.data
            row.remarks = form.remarks.data
            record_action("ATTENDANCE_UPDATED", "Attendance", row.attendance_id)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.attendance_date.errors.append("Duplicate attendance for this employee and date.")
            else:
                flash("Attendance updated.", "success")
                return redirect(url_for("attendance.list_attendance"))
    return render_template("attendance/form.html", form=form, title="Edit attendance")


@bp.get("/reports")
@login_required
def monthly_report():
    month = request.args.get("month", date.today().month, type=int)
    year = request.args.get("year", date.today().year, type=int)
    if month not in range(1, 13) or year not in range(2000, 2201):
        abort(400)
    query = Attendance.query.join(Employee).filter(
        db.extract("month", Attendance.attendance_date) == month,
        db.extract("year", Attendance.attendance_date) == year,
    )
    if current_user.role == "EMPLOYEE":
        if current_user.employee is None:
            abort(403)
        query = query.filter(Attendance.employee_id == current_user.employee.employee_id)
    rows = query.order_by(Attendance.attendance_date, Employee.name).all()
    return render_template(
        "attendance/monthly_report.html", rows=rows, month=month, year=year
    )
