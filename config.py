import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-local-only-secret")
    APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
    DEMO_SEED_ENABLED = os.getenv("DEMO_SEED_ENABLED", "false").strip().lower() == "true"
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///payroll.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    WTF_CSRF_TIME_LIMIT = 3600
    ITEMS_PER_PAGE = 20
    COMPANY_NAME = os.getenv("COMPANY_NAME", "Payroll Management")

    @classmethod
    def validate(cls):
        if not cls.SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY is not configured. Copy .env.example to .env "
                "and set a unique random secret."
            )