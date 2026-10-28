from flask import Blueprint

bp = Blueprint("payroll", __name__, url_prefix="/payroll")

from app.payroll import routes  # noqa: E402,F401
