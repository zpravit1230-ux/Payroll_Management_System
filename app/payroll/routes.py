from datetime import date
from decimal import Decimal
from io import BytesIO

from flask import abort, current_app, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.decorators import roles_required
from app.extensions import db
from app.forms import PayrollGenerateForm
from app.models import AuditLog, Employee, Payroll
from app.payroll import bp
from app.payroll.service import PayrollValidationError, create_payroll, preview_payroll


def can_view(payroll):
    if current_user.role == "EMPLOYEE" and (
        current_user.employee is None
        or current_user.employee.employee_id != payroll.employee_id
    ):
        abort(403)
    if current_user.role not in ("ADMIN", "PAYROLL_OFFICER", "EMPLOYEE"):
        abort(403)


@bp.get("/")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER", "EMPLOYEE")
def list_payroll():
    query = Payroll.query.join(Employee)
    if current_user.role == "EMPLOYEE":
        if current_user.employee is None:
            abort(403)
        query = query.filter(Payroll.employee_id == current_user.employee.employee_id)
    records = query.order_by(Payroll.payroll_year.desc(), Payroll.payroll_month.desc()).limit(500).all()
    return render_template("payroll/list.html", records=records)


@bp.route("/generate", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def generate():
    form = PayrollGenerateForm()
    employees = Employee.query.filter_by(employment_status="ACTIVE").order_by(Employee.name).all()
    form.employee_id.choices = [(0, "Select an employee")] + [
        (e.employee_id, e.name) for e in employees
    ]
    if form.validate_on_submit():
        if not form.employee_id.data:
            form.employee_id.errors.append("Select an employee.")
        else:
            try:
                result = preview_payroll(
                    form.employee_id.data, form.payroll_month.data,
                    form.payroll_year.data, form.bonus.data or Decimal("0")
                )
                return render_template(
                    "payroll/preview.html", result=result,
                    bonus=result["bonus"], month=result["month"], year=result["year"]
                )
            except PayrollValidationError as error:
                form.employee_id.errors.append(str(error))
    return render_template("payroll/generate.html", form=form)


@bp.post("/confirm")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def confirm():
    employee_id = request.form.get("employee_id", type=int)
    month = request.form.get("month", type=int)
    year = request.form.get("year", type=int)
    try:
        bonus = Decimal(request.form.get("bonus", "0"))
        result = preview_payroll(employee_id, month, year, bonus)
        payroll = create_payroll(result, current_user.id)
    except (PayrollValidationError, ValueError, TypeError) as error:
        flash(str(error), "danger")
        return redirect(url_for("payroll.generate"))
    flash("Payroll created and submitted for approval.", "success")
    return redirect(url_for("payroll.detail", payroll_id=payroll.payroll_id))


@bp.get("/<int:payroll_id>")
@login_required
def detail(payroll_id):
    payroll = db.session.get(Payroll, payroll_id)
    if payroll is None:
        abort(404)
    can_view(payroll)
    return render_template("payroll/detail.html", payroll=payroll)


@bp.post("/<int:payroll_id>/approve")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def approve(payroll_id):
    payroll = db.session.get(Payroll, payroll_id)
    if payroll is None:
        abort(404)
    if payroll.payment_status != "PENDING":
        flash("Only pending payroll can be approved.", "warning")
    else:
        payroll.payment_status = "APPROVED"
        db.session.add(AuditLog(
            user_id=current_user.id, action="PAYROLL_APPROVED",
            entity_type="Payroll", entity_id=str(payroll_id)
        ))
        db.session.commit()
        flash("Payroll approved.", "success")
    return redirect(url_for("payroll.detail", payroll_id=payroll_id))


@bp.post("/<int:payroll_id>/mark-paid")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def mark_paid(payroll_id):
    payroll = db.session.get(Payroll, payroll_id)
    if payroll is None:
        abort(404)
    if payroll.payment_status != "APPROVED":
        flash("Only approved payroll can be marked paid.", "warning")
    else:
        payroll.payment_status = "PAID"
        payroll.payment_date = date.today()
        db.session.add(AuditLog(
            user_id=current_user.id, action="PAYROLL_PAID",
            entity_type="Payroll", entity_id=str(payroll_id)
        ))
        db.session.commit()
        flash("Payment recorded.", "success")
    return redirect(url_for("payroll.detail", payroll_id=payroll_id))


@bp.get("/<int:payroll_id>/slip.pdf")
@login_required
def salary_slip(payroll_id):
    payroll = db.session.get(Payroll, payroll_id)
    if payroll is None:
        abort(404)
    can_view(payroll)
    try:
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        y = 750
        lines = [
            current_app.config["COMPANY_NAME"],
            "Salary statement",
            f"Employee: {payroll.employee.name} (ID {payroll.employee_id})",
            f"Department: {payroll.employee.department.department_name if payroll.employee.department else '—'}",
            f"Designation: {payroll.employee.designation}",
            f"Period: {payroll.payroll_month:02d}/{payroll.payroll_year}",
            f"Basic salary: {payroll.basic_salary}",
            f"Allowances: {payroll.allowances}",
            f"Overtime pay: {payroll.overtime_pay}",
            f"Bonus: {payroll.bonus}",
            f"Gross salary: {payroll.gross_salary}",
            "Deductions:",
        ]
        for line in lines:
            pdf.drawString(60, y, line)
            y -= 24
        for deduction in payroll.payroll_taxes:
            pdf.drawString(80, y, f"{deduction.tax_type_snapshot}: {deduction.tax_amount}")
            y -= 20
        for line in (
            f"Total deductions: {payroll.total_deductions}",
            f"Net salary: {payroll.net_salary}",
            f"Payment date: {payroll.payment_date or 'Not paid'}",
            f"Payment status: {payroll.payment_status}",
        ):
            pdf.drawString(60, y, line)
            y -= 24
        pdf.save()
        response = make_response(buffer.getvalue())
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = (
            f'attachment; filename="salary-slip-{payroll.payroll_id}.pdf"'
        )
        return response
    except Exception:
        current_app.logger.exception("Could not generate salary slip %s", payroll_id)
        abort(500)
