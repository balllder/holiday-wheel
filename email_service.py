"""Email service for Holiday Wheel authentication."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Configuration from environment
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "noreply@holidaywheel.com")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"


def send_email(to_email: str, subject: str, html_body: str, text_body: str = None):
    """Send an email via SMTP."""
    if not EMAIL_ENABLED:
        print(f"[DEV EMAIL] To: {to_email}")
        print(f"[DEV EMAIL] Subject: {subject}")
        print(f"[DEV EMAIL] Body: {text_body or html_body}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        if SMTP_USER and SMTP_PASS:
            server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, to_email, msg.as_string())


def send_verification_email(email: str, token: str):
    """Send email verification link."""
    verify_url = f"{BASE_URL}/auth/verify/{token}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
            h1 {{ color: #2b5cff; }}
            .button {{ display: inline-block; background: #2b5cff; color: white; padding: 12px 24px;
                       text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .url {{ word-break: break-all; color: #666; font-size: 12px; }}
            .footer {{ margin-top: 30px; color: #999; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Welcome to Holiday Wheel of Fortune!</h1>
            <p>Please verify your email address to complete your registration.</p>
            <p><a href="{verify_url}" class="button">Verify Email</a></p>
            <p class="url">Or copy this URL: {verify_url}</p>
            <p class="footer">This link expires in 24 hours.<br>
            If you didn't create an account, you can ignore this email.</p>
        </div>
    </body>
    </html>
    """

    text = f"""Welcome to Holiday Wheel of Fortune!

Please verify your email by visiting:
{verify_url}

This link expires in 24 hours.
If you didn't create an account, you can ignore this email.
"""

    send_email(email, "Verify your Holiday Wheel account", html, text)


def send_password_reset_email(email: str, token: str):
    """Send password reset link."""
    reset_url = f"{BASE_URL}/auth/reset-password/{token}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
            h1 {{ color: #2b5cff; }}
            .button {{ display: inline-block; background: #2b5cff; color: white; padding: 12px 24px;
                       text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .url {{ word-break: break-all; color: #666; font-size: 12px; }}
            .footer {{ margin-top: 30px; color: #999; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Password Reset Request</h1>
            <p>Click the button below to reset your password:</p>
            <p><a href="{reset_url}" class="button">Reset Password</a></p>
            <p class="url">Or copy this URL: {reset_url}</p>
            <p class="footer">This link expires in 1 hour.<br>
            If you didn't request a password reset, you can ignore this email.</p>
        </div>
    </body>
    </html>
    """

    text = f"""Password Reset Request

Reset your password by visiting:
{reset_url}

This link expires in 1 hour.
If you didn't request a password reset, you can ignore this email.
"""

    send_email(email, "Reset your Holiday Wheel password", html, text)
