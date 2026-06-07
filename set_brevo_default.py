import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.authentication.models import SystemSettings
from django.conf import settings as django_settings

def set_brevo():
    settings_obj = SystemSettings.get_solo()
    settings_obj.email_provider = "brevo"
    
    api_key = getattr(django_settings, "BREVO_API_KEY", "")
    sender_email = getattr(django_settings, "BREVO_SENDER_EMAIL", "")
    sender_name = getattr(django_settings, "BREVO_SENDER_NAME", "Exposys Data Labs")
    
    brevo_config = settings_obj.brevo_config or {}
    brevo_config["api_key"] = brevo_config.get("api_key") or api_key
    brevo_config["sender_email"] = brevo_config.get("sender_email") or sender_email
    brevo_config["sender_name"] = brevo_config.get("sender_name") or sender_name
    
    settings_obj.brevo_config = brevo_config
    settings_obj.save()
    
    print("Database updated! Email provider is now set to 'brevo'.")
    print(f"Brevo Config: {brevo_config}")

if __name__ == "__main__":
    set_brevo()
