# auth_email.py
import os
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_mail import Message
from werkzeug.security import generate_password_hash

bp = Blueprint("auth_email", __name__)

# ----- token helpers -----
def _serializer():
    secret = current_app.config["SECRET_KEY"]
    return URLSafeTimedSerializer(secret_key=secret, salt="email-flows")

def _make_token(user_id: int, purpose: str) -> str:
    return _serializer().dumps({"uid": user_id, "p": purpose})

def _load_token(token: str, max_age_seconds: int, purpose: str) -> int | None:
    try:
        data = _serializer().loads(token, max_age=max_age_seconds)
    except (SignatureExpired, BadSignature):
        return None
    if not isinstance(data, dict) or data.get("p") != purpose:
        return None
    return data.get("uid")

# ----- email helpers -----
def _send_email(subject: str, recipient: str, html: str, text: str = ""):
    from app import mail  # lazy import to avoid circular import
    msg = Message(
        subject=subject,
        recipients=[recipient],
        html=html,
        body=text,
        sender=current_app.config.get("MAIL_DEFAULT_SENDER", "no-reply@hypertrophy.app"),
    )
    mail.send(msg)

def send_verification_email(user):
    token = _make_token(user.id, "verify")
    url = url_for("auth_email.verify_email", token=token, _external=True)
    html = f"""
    <p>Welcome to Hypertrophy! Confirm your email:</p>
    <p><a href="{url}">Verify my email</a></p>
    <p>This link expires in 24 hours.</p>
    """
    _send_email("Verify your email", user.email, html, f"Verify: {url}")

def send_password_reset_email(user):
    token = _make_token(user.id, "reset")
    url = url_for("auth_email.reset_with_token", token=token, _external=True)
    html = f"""
    <p>Reset your Hypertrophy password:</p>
    <p><a href="{url}">Set a new password</a></p>
    <p>This link expires in 1 hour.</p>
    """
    _send_email("Reset your password", user.email, html, f"Reset: {url}")

# ----- routes -----
@bp.route("/verify/<token>")
def verify_email(token):
    from app import db, User
    uid = _load_token(token, 24 * 3600, "verify")
    if not uid:
        flash("Verification link is invalid or expired.", "warning")
        return redirect(url_for("login"))

    user = db.session.get(User, uid)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("login"))

    if getattr(user, "is_email_verified", False):
        flash("Email already verified.", "info")
    else:
        user.is_email_verified = True
        db.session.commit()
        flash("Email verified. You can log in now.", "success")
    return redirect(url_for("login"))

@bp.route("/request-password-reset", methods=["GET", "POST"])
def request_password_reset():
    from app import User
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter(User.email.ilike(email)).first()
        if user:
            send_password_reset_email(user)
        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("auth_email.request_password_reset"))
    return render_template("request_password_reset.html")

@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_with_token(token):
    from app import db, User
    uid = _load_token(token, 3600, "reset")
    if not uid:
        flash("Reset link is invalid or expired.", "warning")
        return redirect(url_for("auth_email.request_password_reset"))

    user = db.session.get(User, uid)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth_email.request_password_reset"))

    if request.method == "POST":
        pw1 = request.form.get("password") or ""
        pw2 = request.form.get("password2") or ""
        if len(pw1) < 8:
            flash("Password must be at least 8 characters.", "warning")
            return redirect(request.url)
        if pw1 != pw2:
            flash("Passwords do not match.", "warning")
            return redirect(request.url)
        user.password_hash = generate_password_hash(pw1)
        db.session.commit()
        flash("Password updated. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")
