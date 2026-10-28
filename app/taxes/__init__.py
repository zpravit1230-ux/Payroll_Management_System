from flask import Blueprint

bp = Blueprint("taxes", __name__, url_prefix="/taxes")

from app.taxes import routes  # noqa: E402,F401
