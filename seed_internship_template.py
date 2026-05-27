"""Seed the Shortlisted for Internship Program template into the database."""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from apps.templates_engine.models import EmailTemplate
from apps.authentication.models import AdminUser

user = AdminUser.objects.first()

SUBJECT = "Shortlisted for internship Program"

BODY_HTML = """<div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333; max-width: 600px; margin: 0 auto; padding: 20px;">
    
    <p>Dear <strong>{{name}}</strong>,</p>
    
    <p>Thank you for applying for the internship at <strong>Exposys Data Labs</strong>.</p>
    
    <p>We are pleased to inform you that, based on our percentage criteria, your profile has been shortlisted for a one-month internship opportunity.</p>
    
    <p>After the initial internship period, your performance will be evaluated, and successful candidates will proceed to the next level of the interview process for extended roles.</p>
    
    <p>To confirm your participation, a one-time application fee of &#8377;999/month is applicable.</p>
    
    <p><strong>This includes:</strong></p>
    <ul style="list-style: none; padding-left: 0;">
        <li style="margin-bottom: 8px;">&#10004; Project Access</li>
        <li style="margin-bottom: 8px;">&#10004; Technical Support</li>
        <li style="margin-bottom: 8px;">&#10004; Resume Building Guidance</li>
        <li style="margin-bottom: 8px;">&#10004; Internship E-Certificate</li>
        <li style="margin-bottom: 8px;">&#10004; Flexible Timings &amp; Work From Home</li>
    </ul>
    
    <p>&#128073; <strong>Apply Online:</strong><br>
    <a href="http://exposysdata.in/registration.php" style="color: #0d6efd; text-decoration: none;">http://exposysdata.in/registration.php</a></p>
    
    <p>&#128197; <strong>Last Date to Apply:</strong> 25.05.2026</p>
    
    <p>For any queries, feel free to reach out to us.</p>
    
    <p>Warm Regards,<br>
    <strong>Team Exposys Data Labs</strong><br>
    &#127760; <a href="http://www.exposysdata.com" style="color: #0d6efd; text-decoration: none;">www.exposysdata.com</a> | <a href="http://www.exposysdata.in" style="color: #0d6efd; text-decoration: none;">www.exposysdata.in</a><br>
    &#128222; +91 77952 07065 / +91 78920 53145</p>

</div>"""

BODY_PLAIN = """Dear {{name}},

Thank you for applying for the internship at Exposys Data Labs.

We are pleased to inform you that, based on our percentage criteria, your profile has been shortlisted for a one-month internship opportunity.

After the initial internship period, your performance will be evaluated, and successful candidates will proceed to the next level of the interview process for extended roles.

To confirm your participation, a one-time application fee of Rs.999/month is applicable.

This includes:
- Project Access
- Technical Support
- Resume Building Guidance
- Internship E-Certificate
- Flexible Timings & Work From Home

Apply Online: http://exposysdata.in/registration.php

Last Date to Apply: 25.05.2026

For any queries, feel free to reach out to us.

Warm Regards,
Team Exposys Data Labs
www.exposysdata.com | www.exposysdata.in
+91 77952 07065 / +91 78920 53145"""

# Remove any old duplicates
deleted_count, _ = EmailTemplate.objects.filter(name="Shortlisted for Internship Program").delete()
print(f"Cleaned up {deleted_count} old template(s)")

template = EmailTemplate.objects.create(
    name="Shortlisted for Internship Program",
    subject=SUBJECT,
    body_html=BODY_HTML,
    body_plain=BODY_PLAIN,
    created_by=user,
    is_active=True,
)
print(f"Template CREATED successfully!")
print(f"  Name:    {template.name}")
print(f"  Subject: {template.subject}")
print(f"  ID:      {template.id}")

print(f"\nAll active templates in DB:")
for t in EmailTemplate.objects.filter(is_active=True):
    print(f"  - [{t.id}] {t.name} | Subject: {t.subject}")
