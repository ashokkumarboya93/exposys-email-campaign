from typing import Any

class BaseEmailProvider:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    async def send_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Takes a payload dict:
        {
            "campaign_contact_id": "uuid",
            "email": "user@example.com",
            "name": "User",
            "subject": "Subject",
            "body_html": "<p>Hi</p>",
            "body_plain": "Hi"
        }
        Returns:
        {
            "campaign_contact_id": "uuid",
            "status": "sent" | "failed",
            "error": "Error message if any",
            "provider_response": {}
        }
        """
        raise NotImplementedError
