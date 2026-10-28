from flask_wtf import FlaskForm
from wtforms import (
    BooleanField, DateField, DecimalField, IntegerField, PasswordField,
    SelectField, StringField, SubmitField, TextAreaField, TimeField
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, InputRequired, Length, NumberRange, Optional
)


class LoginForm(FlaskForm):
    username = StringField("Username or email", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Sign in")


class EmployeeForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=160)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    department_id = SelectField("Department", coerce=int, validators=[Optional()])
    designation = StringField("Designation", validators=[DataRequired(), Length(max=120)])
    phone = StringField("Phone", validators=[Optional(), Length(max=40)])
    date_of_joining = DateField("Date of joining", validators=[DataRequired()])
    employment_status = SelectField(
        "Status", choices=[("ACTIVE", "Active"), ("INACTIVE", "Inactive")]
    )
    submit = SubmitField("Save employee")


class DepartmentForm(FlaskForm):
    department_name = StringField("Department name", validators=[DataRequired(), Length(max=120)])
    submit = SubmitField("Save department")


class AttendanceForm(FlaskForm):
    employee_id = SelectField("Employee", coerce=int, validators=[DataRequired()])
    attendance_date = DateField("Date", validators=[DataRequired()])
    check_in = TimeField("Check in", validators=[Optional()])
    check_out = TimeField("Check out", validators=[Optional()])
    attendance_status = SelectField(
        "Status",
        choices=[("PRESENT", "Present"), ("ABSENT", "Absent"),
                 ("HALF_DAY", "Half day"), ("LEAVE", "Paid leave"),
                 ("UNPAID_LEAVE", "Unpaid leave")],
    )
    paid_leave = BooleanField("Paid leave")
    overtime_hours = DecimalField(
        "Overtime hours", places=2, default=0,
        validators=[InputRequired(), NumberRange(min=0, max=100)]
    )
    remarks = TextAreaField("Remarks", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save attendance")


class TaxForm(FlaskForm):
    tax_type = StringField("Deduction name", validators=[DataRequired(), Length(max=120)])
    calculation_method = SelectField(
        "Method", choices=[("rate", "Percentage of gross"), ("fixed", "Fixed amount")]
    )
    tax_rate = DecimalField("Rate (%)", places=4, validators=[Optional(), NumberRange(min=0, max=100)])
    fixed_amount = DecimalField("Fixed amount", places=2, validators=[Optional(), NumberRange(min=0)])
    effective_from = DateField("Effective from", validators=[DataRequired()])
    effective_to = DateField("Effective to", validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    description = TextAreaField("Description", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save deduction")


class PayrollGenerateForm(FlaskForm):
    payroll_month = IntegerField("Month", validators=[DataRequired(), NumberRange(min=1, max=12)])
    payroll_year = IntegerField("Year", validators=[DataRequired(), NumberRange(min=2000, max=2200)])
    employee_id = SelectField("Employee", coerce=int, validators=[Optional()])
    bonus = DecimalField("Bonus", places=2, default=0, validators=[InputRequired(), NumberRange(min=0)])
    submit = SubmitField("Preview payroll")


class SalaryStructureForm(FlaskForm):
    basic_salary = DecimalField(
        "Basic salary", places=2, validators=[InputRequired(), NumberRange(min=0)]
    )
    allowances = DecimalField(
        "Allowances", places=2, default=0,
        validators=[InputRequired(), NumberRange(min=0)]
    )
    overtime_rate = DecimalField(
        "Overtime rate", places=2, default=0,
        validators=[InputRequired(), NumberRange(min=0)]
    )
    effective_from = DateField("Effective from", validators=[DataRequired()])
    submit = SubmitField("Save salary structure")


class AdminCreateForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=12)])
    confirm = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Create administrator")


class UserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password (leave blank to keep current password)", validators=[Optional(), Length(min=12)])
    role = SelectField(
        "Role", choices=[
            ("ADMIN", "Administrator"), ("HR", "HR"),
            ("PAYROLL_OFFICER", "Payroll officer"), ("EMPLOYEE", "Employee"),
        ], validators=[DataRequired()]
    )
    employee_id = SelectField("Linked employee", coerce=int, validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save user")