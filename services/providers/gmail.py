import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .base import BaseEmailProvider


class GmailSMTPProvider(BaseEmailProvider):
    """
    Sends emails via Gmail's SMTP server using an App Password.
    Config keys:
        - sender_email: the gmail address
        - app_password: the 16-char app password
        - sender_name: display name (optional)
    """

    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        sender_email = self.config.get("sender_email", "")
        app_password = self.config.get("app_password", "")
        sender_name = self.config.get("sender_name", "Exposys Campaign")

        result = {
            "campaign_contact_id": payload["campaign_contact_id"],
            "contact_id": payload.get("contact_id"),
            "email": payload["email"],
            "subject": payload["subject"],
        }

        def _smtp_send():
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = payload["email"]
            msg["Subject"] = payload["subject"]

            # Plain text part
            if payload.get("body_plain"):
                msg.attach(MIMEText(payload["body_plain"], "plain", "utf-8"))

            # HTML part
            if payload.get("body_html"):
                msg.attach(MIMEText(payload["body_html"], "html", "utf-8"))

            context = ssl.create_default_context()
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(sender_email, app_password)
                server.sendmail(sender_email, payload["email"], msg.as_string())

        try:
            await asyncio.to_thread(_smtp_send)
            result["status"] = "sent"
            result["provider_response"] = {"provider": "gmail_smtp", "message": "OK"}
        except smtplib.SMTPAuthenticationError as e:
            result["status"] = "failed"
            result["error"] = f"Gmail authentication failed: {e}"
        except smtplib.SMTPRecipientsRefused as e:
            result["status"] = "failed"
            result["error"] = f"Recipient refused: {e}"
        except smtplib.SMTPException as e:
            result["status"] = "failed"
            result["error"] = f"SMTP error: {e}"
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        return result
