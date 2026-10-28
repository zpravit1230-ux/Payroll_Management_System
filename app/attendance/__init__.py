from flask import Blueprint

bp = Blueprint("attendance", __name__, url_prefix="/attendance")

from app.attendance import routes  # noqa: E402,F401
