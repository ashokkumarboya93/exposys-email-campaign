"""
Quick test: Send one real email via the Gmail SMTP provider.
Run with: .\venv\Scripts\python.exe test_gmail_send.py
"""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.authentication.models import SystemSettings
from services.providers.factory import EmailProviderFactory
import asyncio

def main():
    # Load config from DB
    settings = SystemSettings.get_solo()
    print(f"Current provider in DB: {settings.email_provider}")
    print(f"Gmail config: {settings.gmail_config}")
    
    gmail_config = settings.gmail_config or {}
    if not gmail_config.get("sender_email") or not gmail_config.get("app_password"):
        print("ERROR: Gmail config is missing in DB!")
        return
    
    provider = EmailProviderFactory.get_provider("gmail", gmail_config)
    print(f"Provider class: {type(provider).__name__}")
    
    # Build a test payload
    test_payload = {
        "campaign_contact_id": "test-123",
        "contact_id": "test-456",
        "email": gmail_config["sender_email"],  # send to yourself
        "name": "Test User",
        "subject": "Exposys Gmail Test - WORKING!",
        "body_html": "<h1>SUCCESS!</h1><p>If you see this, Gmail SMTP is working correctly through the Exposys provider.</p>",
        "body_plain": "SUCCESS! Gmail SMTP is working.",
    }
    
    print(f"\nSending test email to: {test_payload['email']}")
    result = asyncio.run(provider.send_email(test_payload))
    print(f"\nResult: {result}")
    
    if result.get("status") == "sent":
        print("\n✅ EMAIL SENT SUCCESSFULLY! Check your inbox.")
        print("\nNow you must restart run_single_terminal.py:")
        print("  1. Go to the terminal running run_single_terminal.py")
        print("  2. Press Ctrl+C to stop all services")
        print("  3. Run: python run_single_terminal.py")
        print("  4. Then try launching a campaign again")
    else:
        print(f"\n❌ FAILED: {result.get('error')}")

if __name__ == "__main__":
    main()
