import csv
from decimal import Decimal
from io import BytesIO, StringIO

from flask import abort, make_response, render_template, request
from flask_login import login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.decorators import roles_required
from app.extensions import db
from app.models import Attendance, AuditLog, Department, Employee, Payroll, PayrollTax
from app.reports import bp


REPORT_TYPES = (
    "payroll",
    "annual_payroll",
    "employees",
    "departments",
    "attendance",
    "leave",
    "tax",
    "pending_payroll",
    "paid_payroll",
    "department_payroll",
)
REPORT_LABELS = {
    "payroll": "Monthly Payroll Report",
    "annual_payroll": "Annual Payroll Report",
    "employees": "Employee Report",
    "departments": "Department Report",
    "attendance": "Attendance Report",
    "leave": "Leave Report",
    "tax": "Tax Deduction Report",
    "pending_payroll": "Pending Payroll Report",
    "paid_payroll": "Paid Salary Report",
    "department_payroll": "Department-Wise Payroll Report",
}


def totals_row(report_type, totals):
    if not totals:
        return None
    if "amount" in totals:
        return ["TOTAL", "", "", str(totals["amount"])]
    if report_type == "department_payroll":
        return [
            "TOTAL", "", "", str(totals["gross"]), str(totals["deductions"]),
            str(totals["net"]),
        ]
    return [
        "TOTAL", "", "", str(totals["gross"]), str(totals["deductions"]),
        str(totals["net"]), "",
    ]


def filtered_payroll(forced_status=None):
    query = Payroll.query.join(Employee)
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    department_id = request.args.get("department_id", type=int)
    employee_id = request.args.get("employee_id", type=int)
    status = forced_status or request.args.get("status", "")
    if month is not None:
        if month not in range(1, 13):
            abort(400)
        query = query.filter(Payroll.payroll_month == month)
    if year is not None:
        if year not in range(2000, 2201):
            abort(400)
        query = query.filter(Payroll.payroll_year == year)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if employee_id:
        query = query.filter(Payroll.employee_id == employee_id)
    if status:
        if status not in ("PENDING", "APPROVED", "PAID"):
            abort(400)
        query = query.filter(Payroll.payment_status == status)
    return query.order_by(Payroll.payroll_year.desc(), Payroll.payroll_month.desc())


def report_data(report_type):
    if report_type not in REPORT_TYPES:
        abort(400)
    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)
    department_id = request.args.get("department_id", type=int)
    employee_id = request.args.get("employee_id", type=int)
    if month is not None and month not in range(1, 13):
        abort(400)
    if year is not None and year not in range(2000, 2201):
        abort(400)

    if report_type in ("employees", "departments"):
        if report_type == "employees":
            query = Employee.query.outerjoin(Department)
            if department_id:
                query = query.filter(Employee.department_id == department_id)
            if employee_id:
                query = query.filter(Employee.employee_id == employee_id)
            status = request.args.get("status", "")
            if status:
                if status not in ("ACTIVE", "INACTIVE"):
                    abort(400)
                query = query.filter(Employee.employment_status == status)
            rows = query.order_by(Employee.name).limit(1000).all()
            return (
                ["Employee ID", "Employee", "Email", "Department", "Designation", "Status"],
                [[
                    row.employee_id,
                    row.name,
                    row.email,
                    row.department.department_name if row.department else "",
                    row.designation,
                    row.employment_status,
                ] for row in rows],
                {},
            )
        query = Department.query.outerjoin(Employee).group_by(Department.department_id)
        if department_id:
            query = query.filter(Department.department_id == department_id)
        rows = query.with_entities(
            Department.department_id, Department.department_name,
            db.func.count(Employee.employee_id),
        ).order_by(Department.department_name).all()
        return ["Department ID", "Department", "Employees"], [list(row) for row in rows], {}

    if report_type in ("attendance", "leave"):
        query = Attendance.query.join(Employee)
        if month:
            query = query.filter(db.extract("month", Attendance.attendance_date) == month)
        if year:
            query = query.filter(db.extract("year", Attendance.attendance_date) == year)
        if department_id:
            query = query.filter(Employee.department_id == department_id)
        if employee_id:
            query = query.filter(Attendance.employee_id == employee_id)
        if report_type == "leave":
            query = query.filter(Attendance.attendance_status.in_(("LEAVE", "UNPAID_LEAVE")))
        rows = query.order_by(Attendance.attendance_date.desc(), Employee.name).limit(1000).all()
        return (
            ["Date", "Employee", "Department", "Status", "Paid leave", "Hours", "Overtime"],
            [[
                row.attendance_date.isoformat(),
                row.employee.name,
                row.employee.department.department_name if row.employee.department else "",
                row.attendance_status,
                "Yes" if row.paid_leave else "No",
                str(row.working_hours),
                str(row.overtime_hours),
            ] for row in rows],
            {},
        )

    if report_type == "tax":
        query = PayrollTax.query.join(Payroll).join(Employee)
        if month:
            query = query.filter(Payroll.payroll_month == month)
        if year:
            query = query.filter(Payroll.payroll_year == year)
        if department_id:
            query = query.filter(Employee.department_id == department_id)
        if employee_id:
            query = query.filter(Payroll.employee_id == employee_id)
        status = request.args.get("status", "")
        if status:
            if status not in ("PENDING", "APPROVED", "PAID"):
                abort(400)
            query = query.filter(Payroll.payment_status == status)
        rows = query.order_by(Payroll.payroll_year.desc(), Payroll.payroll_month.desc()).limit(1000).all()
        return (
            ["Employee", "Period", "Deduction", "Amount"],
            [[
                row.payroll.employee.name,
                f"{row.payroll.payroll_month:02d}/{row.payroll.payroll_year}",
                row.tax_type_snapshot,
                str(row.tax_amount),
            ] for row in rows],
            {
                "amount": sum(
                    (Decimal(row.tax_amount) for row in rows), Decimal("0")
                )
            },
        )

    forced_status = {
        "pending_payroll": "PENDING",
        "paid_payroll": "PAID",
    }.get(report_type)
    if report_type == "department_payroll":
        query = db.session.query(
            Department.department_name,
            Payroll.payroll_year,
            Payroll.payroll_month,
            db.func.sum(Payroll.gross_salary),
            db.func.sum(Payroll.total_deductions),
            db.func.sum(Payroll.net_salary),
        ).join(Employee, Employee.department_id == Department.department_id)
        query = query.join(Payroll, Payroll.employee_id == Employee.employee_id)
        if month:
            query = query.filter(Payroll.payroll_month == month)
        if year:
            query = query.filter(Payroll.payroll_year == year)
        if department_id:
            query = query.filter(Department.department_id == department_id)
        if employee_id:
            query = query.filter(Employee.employee_id == employee_id)
        status = request.args.get("status", "")
        if status:
            if status not in ("PENDING", "APPROVED", "PAID"):
                abort(400)
            query = query.filter(Payroll.payment_status == status)
        rows = query.group_by(
            Department.department_id, Payroll.payroll_year, Payroll.payroll_month
        ).order_by(Payroll.payroll_year.desc(), Payroll.payroll_month.desc()).limit(1000).all()
        totals = {
            "gross": sum((Decimal(row[3]) for row in rows), Decimal("0")),
            "deductions": sum((Decimal(row[4]) for row in rows), Decimal("0")),
            "net": sum((Decimal(row[5]) for row in rows), Decimal("0")),
        }
        return (
            ["Department", "Year", "Month", "Gross", "Deductions", "Net"],
            [[name, year_value, month_value, str(gross), str(deductions), str(net)]
             for name, year_value, month_value, gross, deductions, net in rows],
            totals,
        )

    records = filtered_payroll(forced_status).limit(1000).all()
    totals = {
        "gross": sum((Decimal(row.gross_salary) for row in records), Decimal("0")),
        "deductions": sum(
            (Decimal(row.total_deductions) for row in records), Decimal("0")
        ),
        "net": sum((Decimal(row.net_salary) for row in records), Decimal("0")),
    }
    return (
        ["Employee", "Department", "Period", "Gross", "Deductions", "Net", "Status"],
        [[
            row.employee.name,
            row.employee.department.department_name if row.employee.department else "",
            f"{row.payroll_month:02d}/{row.payroll_year}",
            str(row.gross_salary),
            str(row.total_deductions),
            str(row.net_salary),
            row.payment_status,
        ] for row in records],
        totals,
    )


@bp.get("/")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def index():
    report_type = request.args.get("report", "payroll")
    headers, rows, totals = report_data(report_type)
    return render_template(
        "reports/index.html", headers=headers, rows=rows, report_type=report_type,
        report_types=REPORT_LABELS,
        totals=totals,
        departments=Department.query.order_by(Department.department_name).all(),
        employees=Employee.query.order_by(Employee.name).all(),
        month=request.args.get("month", ""),
        year=request.args.get("year", ""),
        department_id=request.args.get("department_id", ""),
        employee_id=request.args.get("employee_id", ""),
        status=request.args.get("status", ""),
    )


@bp.get("/payroll.csv")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def payroll_csv():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Employee ID", "Employee", "Department", "Month", "Year",
        "Gross", "Deductions", "Net", "Status", "Payment date"
    ])
    records = filtered_payroll().limit(1000).all()
    totals = {
        "gross": sum((Decimal(record.gross_salary) for record in records), Decimal("0")),
        "deductions": sum(
            (Decimal(record.total_deductions) for record in records), Decimal("0")
        ),
        "net": sum((Decimal(record.net_salary) for record in records), Decimal("0")),
    }
    for record in records:
        writer.writerow([
            record.employee_id,
            record.employee.name,
            record.employee.department.department_name if record.employee.department else "",
            record.payroll_month,
            record.payroll_year,
            record.gross_salary,
            record.total_deductions,
            record.net_salary,
            record.payment_status,
            record.payment_date or "",
        ])
    writer.writerow(["TOTAL", "", "", "", "", totals["gross"], totals["deductions"], totals["net"], "", ""])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = 'attachment; filename="payroll-report.csv"'
    return response


@bp.get("/payroll.pdf")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def payroll_pdf():
    records = filtered_payroll().limit(1000).all()
    totals = {
        "gross": sum((Decimal(record.gross_salary) for record in records), Decimal("0")),
        "deductions": sum(
            (Decimal(record.total_deductions) for record in records), Decimal("0")
        ),
        "net": sum((Decimal(record.net_salary) for record in records), Decimal("0")),
    }
    rows = [[
        "Employee", "Department", "Period", "Gross", "Deductions", "Net", "Status"
    ]]
    for record in records:
        rows.append([
            record.employee.name,
            record.employee.department.department_name if record.employee.department else "-",
            f"{record.payroll_month:02d}/{record.payroll_year}",
            str(record.gross_salary),
            str(record.total_deductions),
            str(record.net_salary),
            record.payment_status,
        ])
    rows.append([
        "TOTAL", "", "", str(totals["gross"]), str(totals["deductions"]),
        str(totals["net"]), "",
    ])

    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=landscape(letter), title="Payroll report"
    )
    table = Table(rows, repeatRows=1)
    styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263b65")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e9eef8")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8cfdb")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if len(rows) > 2:
        styles.append(
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f7fb")])
        )
    table.setStyle(TableStyle(styles))
    document.build([table])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = 'attachment; filename="payroll-report.pdf"'
    return response


@bp.get("/export.csv")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def report_csv():
    report_type = request.args.get("report", "payroll")
    headers, rows, totals = report_data(report_type)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    summary_row = totals_row(report_type, totals)
    if summary_row:
        writer.writerow(summary_row)
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{report_type.replace("_", "-")}-report.csv"'
    )
    return response


@bp.get("/export.pdf")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def report_pdf():
    report_type = request.args.get("report", "payroll")
    headers, rows, totals = report_data(report_type)
    report_rows = [headers] + [[str(value) for value in row] for row in rows]
    summary_row = totals_row(report_type, totals)
    if summary_row:
        report_rows.append(summary_row)
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(letter),
        title=report_type.replace("_", " ").title() + " report",
    )
    table = Table(report_rows, repeatRows=1)
    styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263b65")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8cfdb")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if totals:
        styles.extend([
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e9eef8")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ])
    if len(report_rows) > (2 if totals else 1):
        styles.append(
            ("ROWBACKGROUNDS", (0, 1), (-1, -2 if totals else -1),
             [colors.white, colors.HexColor("#f5f7fb")])
        )
    table.setStyle(TableStyle(styles))
    document.build([table])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{report_type.replace("_", "-")}-report.pdf"'
    )
    return response


@bp.get("/audit")
@login_required
@roles_required("ADMIN")
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(500).all()
    return render_template("reports/audit_logs.html", logs=logs)
