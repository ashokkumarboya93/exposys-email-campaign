import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.campaigns.models import Campaign, EmailLog
from apps.authentication.models import SystemSettings

print('--- Recent Campaigns ---')
for c in Campaign.objects.order_by('-created_at')[:5]:
    print(f'Campaign: {c.name} | Status: {c.status} | Total: {c.total_recipients} | Sent: {c.sent_count} | Failed: {c.failed_count} | Reason: {c.failure_reason}')

print('\n--- System Settings ---')
s = SystemSettings.get_solo()
print(f'Provider: {s.email_provider}')
print(f'Brevo Config: {s.brevo_config}')
print(f'SES Config: {s.ses_config}')

print('\n--- Recent Email Logs ---')
for l in EmailLog.objects.order_by('-timestamp')[:5]:
    print(f'To: {l.contact.email if l.contact else "Unknown"} | Status: {l.status} | Error: {l.error_message}')
