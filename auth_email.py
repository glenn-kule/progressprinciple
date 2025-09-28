# auth_email.py
from flask import Blueprint, current_app, request, redirect, url_for, render_template_string, flash
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

bp = Blueprint("auth_email", __name__, url_prefix="/auth")

# Global references that will be set by init function
db = None
User = None
mail = None

def init_auth_email(flask_app, database, mail_instance, user_model):
    """Initialize the auth_email module with required instances"""
    global db, User, mail
    db = database
    User = user_model
    mail = mail_instance

# ---- token helpers ----
def _serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY", "dev-secret")
    salt = current_app.config.get("SECURITY_PASSWORD_SALT", "dev-salt")
    return URLSafeTimedSerializer(secret_key=secret, salt=salt)

def _make_token(email: str, purpose: str) -> str:
    return _serializer().dumps({"email": email, "purpose": purpose})

def _load_token(token: str, max_age: int, purpose: str) -> str | None:
    try:
        data = _serializer().loads(token, max_age=max_age)
        if data.get("purpose") != purpose:
            return None
        return data.get("email")
    except (BadSignature, SignatureExpired):
        return None

# ---- email sending wrapper (suppresses during dev) ----
def _send_email(subject: str, to_email: str, html: str, dev_label: str):
    suppress = str(current_app.config.get("MAIL_SUPPRESS_SEND", "0")) in ("1", "true", "True")
    default_sender = current_app.config.get("MAIL_DEFAULT_SENDER", "no-reply@hypertrophy.local")

    if suppress:
        # In dev, just show the link so you can click it.
        from markupsafe import Markup
        flash(Markup(f"<div style='word-break:break-all'><strong>DEV EMAIL</strong> — {dev_label}<br>{html}</div>"), "info")
        return

    # Real send (e.g., on Render if you configured SMTP creds)
    msg = Message(subject=subject, sender=default_sender, recipients=[to_email], html=html)
    mail.send(msg)

# ---- public functions for app.py to call after signup ----
def send_verification_email(user):
    token = _make_token(user.email, "verify")
    url = url_for("auth_email.verify_email", token=token, _external=True)
    html = f'Click to verify your account: <a href="{url}">{url}</a>'
    _send_email("Verify your email", user.email, html, f"Verify: <a href='{url}'>{url}</a>")

def send_password_reset_email(user):
    token = _make_token(user.email, "reset")
    url = url_for("auth_email.reset_password", token=token, _external=True)
    html = f'Reset your password: <a href="{url}">{url}</a>'
    _send_email("Reset your password", user.email, html, f"Reset: <a href='{url}'>{url}</a>")

# ---- routes ----
@bp.route("/verify")
def verify_email():
    token = request.args.get("token", "")
    email = _load_token(token, max_age=60 * 60 * 24, purpose="verify")  # 24h
    if not email:
        flash("Invalid or expired token.", "error")
        return redirect(url_for("login"))

    u = User.query.filter_by(email=email).first()
    if not u:
        flash("Account not found.", "error")
        return redirect(url_for("login"))

    u.is_email_verified = True
    db.session.commit()
    flash("Email verified. You can now log in!", "success")
    return redirect(url_for("login"))

@bp.route("/request-password-reset", methods=["GET", "POST"])
def request_password_reset():
    if request.method == "POST":
        email = (request.form.get("email") or "").lower().strip()
        u = User.query.filter_by(email=email).first()
        if u:
            send_password_reset_email(u)
        flash("If that email exists, a reset link has been sent. (In dev, the link appears above.)", "info")
        return redirect(url_for("login"))

    return render_template_string("""
    {% extends "base.html" %}
    {% block content %}
      <h2>Forgot password</h2>
      <div class="card">
        <form method="post">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <label>Email</label>
          <input name="email" type="email" required placeholder="you@domain.com" autocomplete="email">
          <div style="margin-top:8px;">
            <button class="btn-primary" type="submit">Send reset link</button>
            <a class="btn" href="{{ url_for('login') }}">Back to login</a>
          </div>
        </form>
      </div>
    {% endblock %}
    """)

@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.args.get("token", "")
    if request.method == "POST":
        token = request.form.get("token", "")
        email = _load_token(token, max_age=60 * 60, purpose="reset")  # 1h
        if not email:
            flash("Invalid or expired token.", "error")
            return redirect(url_for("auth_email.request_password_reset"))

        pw = request.form.get("password") or ""
        if len(pw) < 6:
            flash("Password too short.", "error")
            return redirect(url_for("auth_email.reset_password", token=token))

        u = User.query.filter_by(email=email).first()
        if not u:
            flash("Account not found.", "error")
            return redirect(url_for("login"))

        u.set_password(pw)
        db.session.commit()
        flash("Password updated. You can now log in.", "success")
        return redirect(url_for("login"))

    # GET
    email = _load_token(token, max_age=60 * 60, purpose="reset")
    if not token or not email:
        flash("Invalid or expired token.", "error")
        return redirect(url_for("auth_email.request_password_reset"))

    return render_template_string("""
    {% extends "base.html" %}
    {% block content %}
      <h2>Set a new password</h2>
      <div class="card">
        <form method="post">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <input type="hidden" name="token" value="{{ request.args.get('token') }}">
          <label>New password</label>
          <input name="password" type="password" required placeholder="••••••••" autocomplete="new-password">
          <div style="margin-top:8px;">
            <button class="btn-primary" type="submit">Update password</button>
            <a class="btn" href="{{ url_for('login') }}">Cancel</a>
          </div>
        </form>
      </div>
    {% endblock %}
    """)