from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.auth import bp
from app.extensions import db
from app.forms import LoginForm
from app.models import User


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = LoginForm()
    if form.validate_on_submit():
        identity = form.username.data.strip()
        user = User.query.filter(
            db.or_(User.username == identity, User.email == identity)
        ).first()
        if user and user.is_active and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data, fresh=True)
            next_page = request.args.get("next")
            if next_page and not next_page.startswith("/") or (
                next_page and next_page.startswith("//")
            ):
                next_page = None
            return redirect(next_page or url_for("dashboard.index"))
        flash("Invalid username/email or password.", "danger")
    return render_template("auth/login.html", form=form)


@bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("auth.login"))