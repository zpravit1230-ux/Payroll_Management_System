from flask import abort, flash, redirect, render_template, url_for
from flask_login import login_required

from app.decorators import roles_required
from app.extensions import db
from app.forms import UserForm
from app.models import Employee, User
from app.users import bp


def configure_form(form):
    linked = [(0, "No linked employee")] + [
        (employee.employee_id, f"{employee.name} (#{employee.employee_id})")
        for employee in Employee.query.order_by(Employee.name).all()
    ]
    form.employee_id.choices = linked


@bp.get("/")
@login_required
@roles_required("ADMIN")
def index():
    users = User.query.order_by(User.username).all()
    return render_template("users/list.html", users=users)


@bp.route("/add", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN")
def add():
    form = UserForm()
    configure_form(form)
    if form.validate_on_submit():
        username, email = form.username.data.strip(), form.email.data.strip().lower()
        if not form.password.data:
            form.password.errors.append("A password is required for a new user.")
        if form.role.data == "EMPLOYEE" and not form.employee_id.data:
            form.employee_id.errors.append("Link an employee account to the employee record.")
        if User.query.filter(
            db.or_(User.username == username, User.email == email)
        ).first():
            form.username.errors.append("Username or email is already in use.")
        elif form.employee_id.data and Employee.query.filter_by(
            employee_id=form.employee_id.data
        ).filter(Employee.user_id.is_not(None)).first():
            form.employee_id.errors.append("That employee is already linked to a user.")
        elif not form.password.errors and not form.employee_id.errors:
            user = User(
                username=username, email=email, role=form.role.data,
                is_active=form.is_active.data,
            )
            try:
                user.set_password(form.password.data)
            except ValueError as error:
                form.password.errors.append(str(error))
            else:
                db.session.add(user)
                db.session.flush()
                if form.employee_id.data:
                    employee = db.session.get(Employee, form.employee_id.data)
                    employee.user_id = user.id
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise
                flash("User created.", "success")
                return redirect(url_for("users.index"))
    return render_template("users/form.html", form=form, title="Add user")


@bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN")
def edit(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    form = UserForm(obj=user)
    configure_form(form)
    if not form.is_submitted():
        form.employee_id.data = user.employee.employee_id if user.employee else 0
    if form.validate_on_submit():
        username, email = form.username.data.strip(), form.email.data.strip().lower()
        conflict = User.query.filter(
            db.or_(User.username == username, User.email == email),
            User.id != user_id,
        ).first()
        if conflict:
            form.username.errors.append("Username or email is already in use.")
        elif form.employee_id.data and Employee.query.filter(
            Employee.employee_id == form.employee_id.data,
            Employee.user_id.is_not(None),
            Employee.user_id != user_id,
        ).first():
            form.employee_id.errors.append("That employee is already linked to a user.")
        else:
            user.username, user.email = username, email
            user.role, user.is_active = form.role.data, form.is_active.data
            if form.role.data == "EMPLOYEE" and not form.employee_id.data:
                form.employee_id.errors.append("Link an employee account to the employee record.")
                return render_template("users/form.html", form=form, title="Edit user")
            if form.password.data:
                try:
                    user.set_password(form.password.data)
                except ValueError as error:
                    form.password.errors.append(str(error))
                    return render_template("users/form.html", form=form, title="Edit user")
            old_employee = user.employee
            if old_employee and old_employee.employee_id != form.employee_id.data:
                old_employee.user_id = None
            if form.employee_id.data:
                employee = db.session.get(Employee, form.employee_id.data)
                employee.user_id = user.id
            db.session.commit()
            flash("User updated.", "success")
            return redirect(url_for("users.index"))
    return render_template("users/form.html", form=form, title="Edit user")
