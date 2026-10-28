from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.audit import record_action
from sqlalchemy import or_

from app.decorators import roles_required
from app.employees import bp
from app.extensions import db
from app.forms import EmployeeForm, SalaryStructureForm
from app.models import Department, Employee, SalaryStructure


def employee_access(employee):
    if current_user.role == "EMPLOYEE" and (
        current_user.employee is None
        or current_user.employee.employee_id != employee.employee_id
    ):
        abort(403)


def populate_departments(form):
    form.department_id.choices = [(0, "No department")] + [
        (d.department_id, d.department_name)
        for d in Department.query.order_by(Department.department_name).all()
    ]


@bp.get("/")
@login_required
def list_employees():
    if current_user.role == "EMPLOYEE":
        return redirect(url_for("employees.detail", employee_id=current_user.employee.employee_id)) if current_user.employee else abort(403)
    query = Employee.query
    search = request.args.get("q", "").strip()
    department_id = request.args.get("department_id", type=int)
    status = request.args.get("status", "").strip()
    if search:
        query = query.filter(or_(Employee.name.ilike(f"%{search}%"), Employee.email.ilike(f"%{search}%"), Employee.employee_id == (int(search) if search.isdigit() else -1)))
    if department_id:
        query = query.filter_by(department_id=department_id)
    if status in ("ACTIVE", "INACTIVE"):
        query = query.filter_by(employment_status=status)
    page = query.order_by(Employee.employee_id.desc()).paginate(
        page=request.args.get("page", 1, type=int), per_page=20, error_out=False
    )
    return render_template(
        "employees/list.html", page=page, search=search,
        departments=Department.query.order_by(Department.department_name).all(),
        department_id=department_id, status=status
    )


@bp.route("/add", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN", "HR")
def add():
    form = EmployeeForm()
    populate_departments(form)
    if form.validate_on_submit():
        if Employee.query.filter_by(email=form.email.data.strip().lower()).first():
            form.email.errors.append("An employee with this email already exists.")
        else:
            employee = Employee(
                name=form.name.data.strip(),
                email=form.email.data.strip().lower(),
                department_id=form.department_id.data or None,
                designation=form.designation.data.strip(),
                phone=form.phone.data.strip() or None,
                date_of_joining=form.date_of_joining.data,
                employment_status=form.employment_status.data,
            )
            db.session.add(employee)
            db.session.flush()
            record_action("EMPLOYEE_CREATED", "Employee", employee.employee_id, employee.email)
            db.session.commit()
            flash("Employee created.", "success")
            return redirect(url_for("employees.detail", employee_id=employee.employee_id))
    return render_template("employees/form.html", form=form, title="Add employee")


@bp.get("/<int:employee_id>")
@login_required
def detail(employee_id):
    employee = db.session.get(Employee, employee_id)
    if employee is None:
        abort(404)
    employee_access(employee)
    payroll_history = sorted(
        employee.payroll_records,
        key=lambda record: (record.payroll_year, record.payroll_month),
        reverse=True,
    )
    return render_template(
        "employees/detail.html", employee=employee, payroll_history=payroll_history
    )


@bp.route("/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN", "HR")
def edit(employee_id):
    employee = db.session.get(Employee, employee_id)
    if employee is None:
        abort(404)
    form = EmployeeForm(obj=employee)
    populate_departments(form)
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        duplicate = Employee.query.filter(
            Employee.email == email, Employee.employee_id != employee_id
        ).first()
        if duplicate:
            form.email.errors.append("An employee with this email already exists.")
        else:
            form.populate_obj(employee)
            employee.email = email
            employee.name = form.name.data.strip()
            employee.department_id = form.department_id.data or None
            employee.designation = form.designation.data.strip()
            employee.phone = form.phone.data.strip() or None
            record_action("EMPLOYEE_UPDATED", "Employee", employee.employee_id, employee.email)
            db.session.commit()
            flash("Employee updated.", "success")
            return redirect(url_for("employees.detail", employee_id=employee_id))
    return render_template("employees/form.html", form=form, title="Edit employee")


@bp.post("/<int:employee_id>/deactivate")
@login_required
@roles_required("ADMIN", "HR")
def deactivate(employee_id):
    employee = db.session.get(Employee, employee_id)
    if employee is None:
        abort(404)
    employee.employment_status = "INACTIVE"
    record_action("EMPLOYEE_DEACTIVATED", "Employee", employee.employee_id)
    db.session.commit()
    flash("Employee deactivated. Historical records were retained.", "success")
    return redirect(url_for("employees.detail", employee_id=employee_id))


@bp.route("/<int:employee_id>/salary", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN")
def salary(employee_id):
    employee = db.session.get(Employee, employee_id)
    if employee is None:
        abort(404)
    form = SalaryStructureForm()
    if form.validate_on_submit():
        latest = SalaryStructure.query.filter_by(employee_id=employee_id).order_by(
            SalaryStructure.effective_from.desc()
        ).first()
        if latest and form.effective_from.data <= latest.effective_from:
            form.effective_from.errors.append(
                "A new salary must start after the current salary record."
            )
        else:
            if latest:
                from datetime import timedelta
                latest.effective_to = form.effective_from.data - timedelta(days=1)
            structure = SalaryStructure(
                employee_id=employee_id,
                basic_salary=form.basic_salary.data,
                allowances=form.allowances.data,
                overtime_rate=form.overtime_rate.data,
                effective_from=form.effective_from.data,
            )
            db.session.add(structure)
            db.session.flush()
            record_action(
                "SALARY_STRUCTURE_CREATED",
                "SalaryStructure",
                structure.salary_structure_id,
                f"Employee ID {employee_id}",
            )
            db.session.commit()
            flash("Salary structure saved. Previous salary history was retained.", "success")
            return redirect(url_for("employees.detail", employee_id=employee_id))
    return render_template("employees/salary.html", form=form, employee=employee)
