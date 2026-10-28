from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.audit import record_action
from app.decorators import roles_required
from app.extensions import db
from app.forms import DepartmentForm
from app.models import Department, Employee
from app.departments import bp


@bp.get("/")
@login_required
def list_departments():
    query = Department.query
    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(Department.department_name.ilike(f"%{search}%"))
    departments = query.order_by(Department.department_name).all()
    return render_template("departments/list.html", departments=departments, search=search)


@bp.get("/<int:department_id>")
@login_required
def detail(department_id):
    department = db.session.get(Department, department_id)
    if department is None:
        abort(404)
    if current_user.role == "EMPLOYEE" and (
        current_user.employee is None
        or current_user.employee.department_id != department_id
    ):
        abort(403)
    if current_user.role == "EMPLOYEE":
        employees = [current_user.employee]
    else:
        employees = Employee.query.filter_by(
            department_id=department_id
        ).order_by(Employee.name).all()
    return render_template(
        "departments/detail.html", department=department, employees=employees
    )


@bp.route("/add", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN")
def add():
    form = DepartmentForm()
    if form.validate_on_submit():
        name = form.department_name.data.strip()
        if Department.query.filter_by(department_name=name).first():
            form.department_name.errors.append("That department already exists.")
        else:
            department = Department(department_name=name)
            db.session.add(department)
            db.session.flush()
            record_action("DEPARTMENT_CREATED", "Department", department.department_id, name)
            db.session.commit()
            flash("Department created.", "success")
            return redirect(url_for("departments.list_departments"))
    return render_template("departments/form.html", form=form, title="Add department")


@bp.route("/<int:department_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN")
def edit(department_id):
    department = db.session.get(Department, department_id)
    if department is None:
        abort(404)
    form = DepartmentForm(obj=department)
    if form.validate_on_submit():
        name = form.department_name.data.strip()
        duplicate = Department.query.filter(
            Department.department_name == name,
            Department.department_id != department_id,
        ).first()
        if duplicate:
            form.department_name.errors.append("That department already exists.")
        else:
            department.department_name = name
            record_action("DEPARTMENT_UPDATED", "Department", department.department_id, name)
            db.session.commit()
            flash("Department updated.", "success")
            return redirect(url_for("departments.list_departments"))
    return render_template("departments/form.html", form=form, title="Edit department")
