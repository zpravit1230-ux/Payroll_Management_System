# Payroll Management System

A local Flask payroll application with user authentication, role-based access,
employee and department records, attendance, versioned salary structures,
configurable deductions, payroll review/approval/payment, salary-slip PDFs,
and filtered payroll CSV exports.

**Important:** payroll calculations are configurable application logic, not
legal/tax advice. Configure deduction rules for the jurisdiction and period
before generating payroll. The application currently uses the selected salary
structure's monthly basic salary and allowances without automatically reducing
pay for absences. Overnight shifts, leave accrual, payment-provider integration,
and adjustment/reversal workflows are not implemented.

## Requirements

- Python 3.11 or newer supported Python 3
- MySQL 8 (or compatible) for a normal deployment
- Visual Studio Code (optional)

SQLite is supported for isolated local tests and can be used for a quick
single-user evaluation, but MySQL is the documented application database.

## Windows PowerShell setup

1. Install Python and MySQL Server. Create a database and a least-privileged
   MySQL user:

   ```sql
   CREATE DATABASE payroll_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'payroll_user'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
   GRANT ALL PRIVILEGES ON payroll_db.* TO 'payroll_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

2. Open this folder in VS Code and create/activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use `Set-ExecutionPolicy -Scope Process
   -ExecutionPolicy Bypass` for that terminal session, then activate again.

3. Install dependencies and configure secrets:

   ```powershell
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

   Edit `.env`. Set a unique `SECRET_KEY`, `DATABASE_URL`, and `COMPANY_NAME`.
   The MySQL URL format is
   `mysql+pymysql://USER:URL_ENCODED_PASSWORD@127.0.0.1:3306/payroll_db?charset=utf8mb4`.
   Replace the example user and password with your local MySQL credentials.
   Every application module uses this one configured URL. If its connection
   fails, the app does not silently switch databases.
   Generate a secret in PowerShell with:

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   URL-encode special characters in the MySQL password in `DATABASE_URL`.

4. Apply the included initial migration. The migration repository is already
   initialized; do **not** run `db init` again:

   ```powershell
   flask --app run.py db upgrade
   ```

   Only if you are initializing an empty project that has no
   `migrations\env.py`, run `flask --app run.py db init` once, then
   `flask --app run.py db migrate -m "Initial schema"` and `flask --app run.py db upgrade`.

   For later model changes, run `flask --app run.py db migrate -m "Describe change"`
   followed by `flask --app run.py db upgrade`. Review generated migration
   scripts before applying them. `schema.sql` points to migrations as the
   authoritative schema source.

5. Verify the database connection and schema version:

   ```powershell
   python scripts\check_database.py --require-mysql
   ```

   This connects to the configured database, executes a query, checks required
   tables, and confirms the Alembic migration is current.

6. Create an administrator securely. The interactive script prompts for the
   password without echoing it; alternatively set `ADMIN_USERNAME`,
   `ADMIN_EMAIL`, and `ADMIN_PASSWORD` in the process environment for a
   one-time run:

   ```powershell
   python scripts\create_admin.py
   ```

7. To add connected development sample records, set `APP_ENV=development` and
   `DEMO_SEED_ENABLED=true` in `.env`, then run the explicit confirmation
   command. If the `.env` intentionally points to the local file-backed
   SQLite evaluation database instead of MySQL, explicitly add
   `--allow-sqlite`:

   ```powershell
   python scripts\seed_demo_data.py --confirm-demo-data
   # SQLite development database only:
   python scripts\seed_demo_data.py --confirm-demo-data --allow-sqlite
   ```

   The seed script prompts once for a password (minimum 12 characters) for
   newly created demo accounts. For a non-interactive local run, set
   `DEMO_ACCOUNT_PASSWORD` in the current terminal before running it. Existing
   users and business records are preserved. Demo usernames are `admin`,
   `hr_manager`, `payroll_officer`, and `employee_demo`. Existing account
   passwords are never changed; use the administrator password previously
   configured if `admin` already exists. Seeded deduction rules are
   illustrative only, not statutory tax advice. Do not enable seeding in
   production. The SQLite option is restricted to a file inside the app's
   `instance` directory; it does not silently change the configured database.

   In a development database, you can remove only the reserved demo emails,
   demo rule names, and the records linked to those seeded employees with:

   ```powershell
   python scripts\seed_demo_data.py --confirm-demo-data --clear-demo
   ```

   The command asks you to type `CLEAR DEMO` before deleting. Review the target
   database and back it up first; never use demo cleanup against production.

8. Start the application and open <http://127.0.0.1:5000>:

   ```powershell
   python run.py
   ```

## Tests

Tests use a temporary in-memory SQLite database and do not contact or mutate
the configured MySQL database:

```powershell
python -m pytest
```

## Common issues

- **MySQL connection/credential error:** ensure the service is running; verify
  database name, user grants, host/port, and URL-encoded password in `.env`.
  Run `python scripts\check_database.py --require-mysql` to validate the
  configured MySQL connection and migration state. The application does not
  switch databases after a connection error. Demo seeding rejects SQLite and
  any database other than `payroll_db`.
- **Missing package:** activate `.venv` and run
  `python -m pip install -r requirements.txt`.
- **Port 5000 in use:** stop the other local application or change the port in
  `run.py`.
- **Missing secret/environment variable:** make sure `.env` is in the project
  root and contains a random `SECRET_KEY` and valid `DATABASE_URL`.
- **Import/template error:** run commands from the project root with the
  project's virtual environment active.
- **Migration command error:** check that `migrations\env.py` exists; only run
  `flask --app run.py db init` when initializing migrations for the first time.
  Review migration output before upgrade and take a database backup first.

## Current workflow and limitations

- Supported roles: `ADMIN`, `HR`, `PAYROLL_OFFICER`, and `EMPLOYEE`. An admin
  can create user accounts and link employee accounts from **User accounts**.
- Payroll starts in `PENDING`, can be approved, then marked `PAID`. These
  changes are audited. Saved payroll amounts and itemized deduction names and
  values are used for salary slips; payroll rows are not recalculated on view.
- Each active deduction rule effective in the period is applied. With no
  effective deduction rule, payroll generation is blocked for explicit
  configuration rather than assuming a tax rate.
- Salary structures are effective-dated; prior history is closed when a new
  salary is added. Configure attendance/overtime and deduction rules before
  payroll.
- Reports include employee, department, attendance, leave, monthly/annual
  payroll, tax deduction, pending payroll, paid payroll, and department-wise
  payroll views, with CSV and PDF exports using the same filtered records.
- Dashboard charts are queried from database records, and administrative
  create/update/payroll actions are available in the audit log.
- The development seed script creates example departments, employees,
  versioned salaries, attendance, demo deductions, payroll calculated by the
  application service, role-linked users, and audit entries.