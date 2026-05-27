import os
import django

def seed():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    from django.conf import settings
    from apps.authentication.models import SystemSettings
    
    s = SystemSettings.get_solo()
    
    # Read from environment via Django settings
    api_key = getattr(settings, 'BREVO_API_KEY', '')
    sender_email = getattr(settings, 'BREVO_SENDER_EMAIL', '')
    sender_name = getattr(settings, 'BREVO_SENDER_NAME', 'Exposys Campaign')
    
    if not api_key:
        print("Warning: BREVO_API_KEY is not set in .env")
        
    brevo = s.brevo_config or {}
    brevo['api_key'] = api_key
    brevo['sender_email'] = sender_email
    brevo['sender_name'] = sender_name
    
    s.brevo_config = brevo
    s.email_provider = 'brevo'
    s.save()
    
    print("Seeded SystemSettings with Brevo Config:")
    print(f"API Key: {api_key[:10]}... (len: {len(api_key)})")
    print(f"Sender Email: {sender_email}")
    print(f"Sender Name: {sender_name}")

if __name__ == "__main__":
    seed()
