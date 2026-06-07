import os
import sys
import django
import asyncio

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.authentication.models import SystemSettings
from services.providers.factory import EmailProviderFactory
from django.conf import settings as django_settings

def main():
    settings = SystemSettings.get_solo()
    print(f"Current provider in DB: {settings.email_provider}")
    
    brevo_config = settings.brevo_config or {}
    
    # Fallback to .env / django settings if DB is empty
    api_key = brevo_config.get("api_key") or getattr(django_settings, "BREVO_API_KEY", "")
    sender_email = brevo_config.get("sender_email") or getattr(django_settings, "BREVO_SENDER_EMAIL", "")
    sender_name = brevo_config.get("sender_name") or getattr(django_settings, "BREVO_SENDER_NAME", "Exposys Campaign")

    print(f"Brevo DB Config: {brevo_config}")
    print(f"Using API Key: {api_key[:10]}...{api_key[-5:] if api_key else ''}")
    print(f"Using Sender Email: {sender_email}")
    
    if not api_key or not sender_email:
        print("ERROR: Brevo config is missing API Key or Sender Email!")
        return
    
    config = {
        "api_key": api_key,
        "sender_email": sender_email,
        "sender_name": sender_name,
    }
    
    provider = EmailProviderFactory.get_provider("brevo", config)
    print(f"Provider class: {type(provider).__name__}")
    
    test_payload = {
        "campaign_contact_id": "test-123",
        "contact_id": "test-456",
        "email": sender_email,  # Send to yourself for testing
        "name": "Test User",
        "subject": "Exposys Brevo Test - WORKING!",
        "body_html": "<h1>SUCCESS!</h1><p>If you see this, Brevo is working correctly through the Exposys provider.</p>",
        "body_plain": "SUCCESS! Brevo is working.",
    }
    
    print(f"\nSending test email to: {test_payload['email']}")
    result = asyncio.run(provider.send_email(test_payload))
    print(f"\nResult: {result}")
    
    if result.get("status") == "sent":
        print("\n✅ EMAIL SENT SUCCESSFULLY! Check your inbox.")
    else:
        print(f"\n❌ FAILED: {result.get('error')}")

if __name__ == "__main__":
    main()
