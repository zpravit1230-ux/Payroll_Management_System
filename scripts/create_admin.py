import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import User


def main():
    app = create_app()
    with app.app_context():
        username = os.getenv("ADMIN_USERNAME") or input("Administrator username: ").strip()
        email = os.getenv("ADMIN_EMAIL") or input("Administrator email: ").strip().lower()
        password = os.getenv("ADMIN_PASSWORD") or getpass.getpass("Administrator password: ")
        if not username or not email or not password:
            raise SystemExit("Username, email, and password are required.")
        if User.query.filter(
            db.or_(User.username == username, User.email == email)
        ).first():
            raise SystemExit("A user with that username or email already exists.")
        user = User(username=username, email=email, role="ADMIN")
        try:
            user.set_password(password)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        db.session.add(user)
        db.session.commit()
        print("Administrator created.")


if __name__ == "__main__":
    main()