import click
from flask.cli import with_appcontext

from app import create_app
from app.extensions import db
from app.models import User

app = create_app()


@app.cli.command("create-admin")
@click.option("--username", prompt=True)
@click.option("--email", prompt=True)
@click.password_option("--password", confirmation_prompt=True)
@with_appcontext
def create_admin(username, email, password):
    """Create an administrator without a default password."""
    if User.query.filter(
        db.or_(User.username == username, User.email == email)
    ).first():
        raise click.ClickException("A user with this username or email already exists.")
    user = User(username=username.strip(), email=email.strip().lower(), role="ADMIN")
    try:
        user.set_password(password)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    db.session.add(user)
    db.session.commit()
    click.echo("Administrator created.")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)