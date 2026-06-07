import json
import urllib.request
import urllib.error
import asyncio
from typing import Any
from .base import BaseEmailProvider

class BrevoProvider(BaseEmailProvider):
    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = self.config.get("api_key")
        sender_email = self.config.get("sender_email")
        sender_name = self.config.get("sender_name")

        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        }

        body = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": payload["email"], "name": payload["name"]}],
            "subject": payload["subject"],
            "htmlContent": payload["body_html"],
        }
        if payload.get("body_plain"):
            body["textContent"] = payload["body_plain"]

        result = {
            "campaign_contact_id": payload["campaign_contact_id"],
            "contact_id": payload.get("contact_id"),
            "email": payload["email"],
            "subject": payload["subject"],
        }

        try:
            req = urllib.request.Request("https://api.brevo.com/v3/smtp/email", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            
            def _make_request():
                try:
                    with urllib.request.urlopen(req) as response:
                        return response.status, json.loads(response.read().decode())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read().decode()) if e.read() else {}
            
            status_code, resp_data = await asyncio.to_thread(_make_request)
            
            if status_code in (200, 201, 202):
                result["status"] = "sent"
                result["provider_response"] = resp_data
            elif status_code == 429:
                result["status"] = "failed"
                result["error"] = "Rate limit exceeded"
                result["deferred"] = True
            else:
                result["status"] = "failed"
                result["error"] = resp_data.get("message", f"HTTP {status_code}")
        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            
        return result
