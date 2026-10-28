from flask import abort, flash, redirect, render_template, url_for
from flask_login import login_required

from app.audit import record_action
from app.decorators import roles_required
from app.extensions import db
from app.forms import TaxForm
from app.models import Tax
from app.taxes import bp


def save_tax(form, tax=None):
    if form.effective_to.data and form.effective_to.data < form.effective_from.data:
        form.effective_to.errors.append("End date must be on or after the start date.")
        return False
    if form.calculation_method.data == "rate":
        if form.tax_rate.data is None or form.fixed_amount.data is not None:
            form.tax_rate.errors.append("Enter a percentage rate only.")
            return False
        rate, fixed = form.tax_rate.data, None
    else:
        if form.fixed_amount.data is None or form.tax_rate.data is not None:
            form.fixed_amount.errors.append("Enter a fixed amount only.")
            return False
        rate, fixed = None, form.fixed_amount.data
    if tax is None:
        tax = Tax()
        db.session.add(tax)
    tax.tax_type = form.tax_type.data.strip()
    tax.tax_rate = rate
    tax.fixed_amount = fixed
    tax.effective_from = form.effective_from.data
    tax.effective_to = form.effective_to.data
    tax.is_active = form.is_active.data
    tax.description = form.description.data
    db.session.flush()
    record_action("TAX_RULE_SAVED", "Tax", tax.tax_id, tax.tax_type)
    db.session.commit()
    return True


@bp.get("/")
@login_required
@roles_required("ADMIN", "PAYROLL_OFFICER")
def list_taxes():
    taxes = Tax.query.order_by(Tax.effective_from.desc(), Tax.tax_type).all()
    return render_template("taxes/list.html", taxes=taxes)


@bp.route("/add", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN")
def add():
    form = TaxForm()
    if form.validate_on_submit() and save_tax(form):
        flash("Deduction rule saved.", "success")
        return redirect(url_for("taxes.list_taxes"))
    return render_template("taxes/form.html", form=form, title="Add deduction rule")


@bp.route("/<int:tax_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("ADMIN")
def edit(tax_id):
    tax = db.session.get(Tax, tax_id)
    if tax is None:
        abort(404)
    form = TaxForm(obj=tax)
    if not form.is_submitted():
        form.calculation_method.data = "rate" if tax.tax_rate is not None else "fixed"
    if form.validate_on_submit() and save_tax(form, tax):
        flash("Deduction rule updated. Existing payroll deductions remain unchanged.", "success")
        return redirect(url_for("taxes.list_taxes"))
    return render_template("taxes/form.html", form=form, title="Edit deduction rule")
