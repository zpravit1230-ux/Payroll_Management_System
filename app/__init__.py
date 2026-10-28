import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy.exc import OperationalError

from config import Config
from app.extensions import csrf, db, login_manager, migrate


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    elif not app.testing:
        Config.validate()

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    from app import models  # noqa: F401
    from app.auth import bp as auth_bp
    from app.attendance import bp as attendance_bp
    from app.dashboard import bp as dashboard_bp
    from app.departments import bp as departments_bp
    from app.employees import bp as employees_bp
    from app.payroll import bp as payroll_bp
    from app.reports import bp as reports_bp
    from app.taxes import bp as taxes_bp
    from app.users import bp as users_bp

    for blueprint in (
        auth_bp,
        dashboard_bp,
        employees_bp,
        departments_bp,
        attendance_bp,
        payroll_bp,
        taxes_bp,
        reports_bp,
        users_bp,
    ):
        app.register_blueprint(blueprint)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(OperationalError)
    def database_error(error):
        app.logger.exception("Database operation failed: %s", error)
        db.session.rollback()
        flash(
            "The database could not be reached. Check your database settings "
            "and ensure the database server is running.",
            "danger",
        )
        return render_template("errors/500.html"), 500

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled application error: %s", error)
        return render_template("errors/500.html"), 500

    if not app.testing:
        handler = RotatingFileHandler(
            Path(app.instance_path) / "payroll.log",
            maxBytes=1_000_000,
            backupCount=3,
        )
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)

    return app