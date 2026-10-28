import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db


def main():
    parser = argparse.ArgumentParser(description="Verify the configured database.")
    parser.add_argument(
        "--require-mysql",
        action="store_true",
        help="Require MySQL and the payroll_db database instead of checking any backend.",
    )
    args = parser.parse_args()
    app = create_app()
    root = Path(__file__).resolve().parents[1]
    alembic_config = AlembicConfig()
    alembic_config.set_main_option("script_location", str(root / "migrations"))
    scripts = ScriptDirectory.from_config(alembic_config)

    print("Payroll Management System - Database Check")
    print("Application configuration: Loaded")
    try:
        with app.app_context():
            if args.require_mysql:
                backend = db.engine.url.get_backend_name()
                database = db.engine.url.database
                if backend != "mysql" or database != "payroll_db":
                    raise RuntimeError(
                        "Expected MySQL database `payroll_db`, but the active "
                        f"configuration targets backend `{backend}` and database `{database}`. "
                        "Update DATABASE_URL in the project .env. No fallback was attempted."
                    )
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
                inspector = inspect(connection)
                tables = set(inspector.get_table_names())
                missing_tables = set(db.metadata.tables) - tables
                if missing_tables:
                    raise RuntimeError(
                        "Missing schema tables: " + ", ".join(sorted(missing_tables))
                    )
                current_heads = set(MigrationContext.configure(connection).get_current_heads())
                expected_heads = set(scripts.get_heads())
                if not current_heads:
                    raise RuntimeError(
                        "No migration revision is recorded. Run `flask --app run.py db upgrade`."
                    )
                if current_heads != expected_heads:
                    raise RuntimeError(
                        "Database schema is not at the latest migration. "
                        "Run `flask --app run.py db upgrade`."
                    )
                db_name = db.engine.url.database or "main"
                if db.engine.dialect.name == "mysql":
                    db_name = connection.execute(text("SELECT DATABASE()")).scalar_one()
                print("Database connection: Successful")
                print(f"Database name: {db_name}")
                print("Database query: Successful")
                print("Database schema: Up to date")
                print("Database verification completed.")
    except (SQLAlchemyError, RuntimeError) as error:
        print(f"Database verification failed: {error}", file=sys.stderr)
        if isinstance(error, SQLAlchemyError):
            print(
                "Check that the configured database server is running, the database exists, "
                "and DATABASE_URL credentials are correct.",
                file=sys.stderr,
            )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
