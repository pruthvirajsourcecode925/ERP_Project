from email.message import EmailMessage
import smtplib

from app.core.config import settings


def can_send_email() -> bool:
    return all([
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        settings.SMTP_USERNAME,
        settings.SMTP_PASSWORD,
        settings.SMTP_FROM_EMAIL,
    ])


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    if not can_send_email():
        return False

    msg = EmailMessage()
    msg["Subject"] = "Password Reset"
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(
        "Use the link below to reset your password:\n\n"
        f"{reset_link}\n\n"
        "If you did not request this, ignore this email."
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)

    return True
