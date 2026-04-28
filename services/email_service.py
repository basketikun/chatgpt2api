from __future__ import annotations

import smtplib
from email.message import EmailMessage

from services.user_service import UserServiceError, clean_string


class EmailService:
    def send_verification_code(self, email: str, code: str) -> None:
        from services.user_service import user_service

        settings = user_service.get_settings()
        host = clean_string(settings.get("smtp_host"))
        if not host:
            raise UserServiceError("SMTP is not configured", status_code=400, code="smtp_not_configured")
        port = int(settings.get("smtp_port") or 587)
        username = clean_string(settings.get("smtp_username"))
        password = clean_string(settings.get("smtp_password"))
        sender = clean_string(settings.get("smtp_from")) or username
        if not sender:
            raise UserServiceError("SMTP sender is not configured", status_code=400, code="smtp_not_configured")

        message = EmailMessage()
        message["Subject"] = "chatgpt2api verification code"
        message["From"] = sender
        message["To"] = email
        message.set_content(f"Your verification code is {code}. It expires in 15 minutes.")

        use_tls = bool(settings.get("smtp_tls", True))
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)


email_service = EmailService()
