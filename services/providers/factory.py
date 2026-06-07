from typing import Any
from .base import BaseEmailProvider
from .ses import AmazonSESProvider
from .brevo import BrevoProvider
from .gmail import GmailSMTPProvider

class EmailProviderFactory:
    @staticmethod
    def get_provider(provider_name: str, config: dict[str, Any]) -> BaseEmailProvider:
        if provider_name.lower() == "ses":
            return AmazonSESProvider(config)
        elif provider_name.lower() == "brevo":
            return BrevoProvider(config)
        elif provider_name.lower() == "gmail":
            return GmailSMTPProvider(config)
        else:
            raise ValueError(f"Unknown email provider: {provider_name}")
