import pytest

from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-key-that-is-only-for-tests",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "WTF_CSRF_ENABLED": False,
    })
    with application.app_context():
        db.create_all()
        admin = User(username="admin", email="admin@example.test", role="ADMIN")
        admin.set_password("a-long-test-password")
        db.session.add(admin)
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
