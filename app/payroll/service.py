from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Attendance, AuditLog, Employee, Payroll, PayrollTax, SalaryStructure, Tax
)

CENT = Decimal("0.01")


class PayrollValidationError(ValueError):
    pass


def money(value):
    result = Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    if not result.is_finite() or result < 0:
        raise PayrollValidationError("Payroll amounts must be finite and non-negative.")
    return result


def preview_payroll(employee_id, month, year, bonus=Decimal("0")):
    if month not in range(1, 13) or year not in range(2000, 2201):
        raise PayrollValidationError("Select a valid payroll month and year.")
    employee = db.session.get(Employee, employee_id)
    if employee is None or employee.employment_status != "ACTIVE":
        raise PayrollValidationError("Select an active employee.")
    if Payroll.query.filter_by(
        employee_id=employee_id, payroll_month=month, payroll_year=year
    ).first():
        raise PayrollValidationError("Payroll already exists for this employee and period.")
    period_start = date(year, month, 1)
    period_end = date(year, month, monthrange(year, month)[1])
    salaries = SalaryStructure.query.filter(
        SalaryStructure.employee_id == employee_id,
        SalaryStructure.effective_from <= period_end,
        db.or_(
            SalaryStructure.effective_to.is_(None),
            SalaryStructure.effective_to >= period_start,
        ),
    ).order_by(SalaryStructure.effective_from.desc()).all()
    if not salaries:
        raise PayrollValidationError("No salary structure is configured for this period.")
    salary = salaries[0]
    attendance = Attendance.query.filter(
        Attendance.employee_id == employee_id,
        Attendance.attendance_date >= period_start,
        Attendance.attendance_date <= period_end,
    ).all()
    overtime_hours = sum(
        (Decimal(row.overtime_hours or 0) for row in attendance), Decimal("0")
    )
    basic = money(salary.basic_salary)
    allowances = money(salary.allowances)
    overtime_pay = money(overtime_hours * Decimal(salary.overtime_rate))
    bonus = money(bonus)
    gross = money(basic + allowances + overtime_pay + bonus)
    taxes = Tax.query.filter(
        Tax.is_active.is_(True),
        Tax.effective_from <= period_end,
        db.or_(Tax.effective_to.is_(None), Tax.effective_to >= period_start),
    ).order_by(Tax.tax_id).all()
    if not taxes:
        raise PayrollValidationError(
            "No active deduction rule applies to this payroll period. Configure tax rules first."
        )
    deductions = []
    total_deductions = Decimal("0")
    for tax in taxes:
        amount = (
            gross * Decimal(tax.tax_rate) / Decimal("100")
            if tax.tax_rate is not None else Decimal(tax.fixed_amount)
        )
        amount = money(amount)
        deductions.append({"tax": tax, "amount": amount})
        total_deductions += amount
    total_deductions = money(total_deductions)
    if total_deductions > gross:
        raise PayrollValidationError("Configured deductions exceed gross salary.")
    return {
        "employee": employee,
        "month": month,
        "year": year,
        "basic": basic,
        "allowances": allowances,
        "overtime_pay": overtime_pay,
        "bonus": bonus,
        "gross": gross,
        "deductions": deductions,
        "total_deductions": total_deductions,
        "net": money(gross - total_deductions),
    }


def create_payroll(preview, actor_id):
    employee = preview["employee"]
    if Payroll.query.filter_by(
        employee_id=employee.employee_id,
        payroll_month=preview["month"],
        payroll_year=preview["year"],
    ).first():
        raise PayrollValidationError("Payroll already exists for this employee and period.")
    try:
        payroll = Payroll(
            employee_id=employee.employee_id,
            payroll_month=preview["month"],
            payroll_year=preview["year"],
            basic_salary=preview["basic"],
            allowances=preview["allowances"],
            overtime_pay=preview["overtime_pay"],
            bonus=preview["bonus"],
            gross_salary=preview["gross"],
            total_deductions=preview["total_deductions"],
            net_salary=preview["net"],
            payment_status="PENDING",
        )
        db.session.add(payroll)
        db.session.flush()
        for item in preview["deductions"]:
            db.session.add(PayrollTax(
                payroll_id=payroll.payroll_id,
                tax_id=item["tax"].tax_id,
                tax_amount=item["amount"],
                tax_type_snapshot=item["tax"].tax_type,
            ))
        db.session.add(AuditLog(
            user_id=actor_id, action="PAYROLL_GENERATED", entity_type="Payroll",
            entity_id=str(payroll.payroll_id),
            details=f"{employee.name}: {preview['month']}/{preview['year']}",
        ))
        db.session.commit()
        return payroll
    except IntegrityError as error:
        db.session.rollback()
        raise PayrollValidationError(
            "Payroll already exists for this employee and period."
        ) from error
    except Exception:
        db.session.rollback()
        raise
