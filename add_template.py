import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.templates_engine.models import EmailTemplate

html_content = """
<div style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
    <p>Dear <strong>{{name}}</strong>,</p>
    
    <p>Thank you for applying for the internship at Exposys Data Labs.</p>
    
    <p>We are pleased to inform you that, based on our percentage criteria, your profile has been shortlisted for a one-month internship opportunity.</p>
    
    <p>After the initial internship period, your performance will be evaluated, and successful candidates will proceed to the next level of the interview process for extended roles.</p>
    
    <p>To confirm your participation, a one-time application fee of <strong>₹999/month</strong> is applicable.</p>
    
    <p>This includes:</p>
    <ul style="list-style: none; padding-left: 0;">
        <li>✅ Project Access</li>
        <li>✅ Technical Support</li>
        <li>✅ Resume Building Guidance</li>
        <li>✅ Internship E-Certificate</li>
        <li>✅ Flexible Timings & Work From Home</li>
    </ul>
    
    <p>👉 <strong>Apply Online:</strong><br>
    <a href="http://exposysdata.in/registration.php" style="color: #0ea5e9; text-decoration: none;">http://exposysdata.in/registration.php</a></p>
    
    <p>📅 <strong>Last Date to Apply:</strong> 25.05.2026</p>
    
    <p>For any queries, feel free to reach out to us.</p>
    
    <p>Warm Regards,<br>
    <strong>Team Exposys Data Labs</strong><br>
    🌐 <a href="http://www.exposysdata.com" style="color: #0ea5e9;">www.exposysdata.com</a> | <a href="http://www.exposysdata.in" style="color: #0ea5e9;">www.exposysdata.in</a><br>
    📞 +91 77952 07065 / +91 78920 53145</p>
</div>
"""

plain_text = """
Dear {{name}},

Thank you for applying for the internship at Exposys Data Labs.
We are pleased to inform you that, based on our percentage criteria, your profile has been shortlisted for a one-month internship opportunity.
After the initial internship period, your performance will be evaluated, and successful candidates will proceed to the next level of the interview process for extended roles.
To confirm your participation, a one-time application fee of ₹999/month is applicable.

This includes:
✅ Project Access
✅ Technical Support
✅ Resume Building Guidance
✅ Internship E-Certificate
✅ Flexible Timings & Work From Home

👉 Apply Online:
http://exposysdata.in/registration.php

📅 Last Date to Apply: 25.05.2026

For any queries, feel free to reach out to us.

Warm Regards,
Team Exposys Data Labs
🌐 www.exposysdata.com | www.exposysdata.in
📞 +91 77952 07065 / +91 78920 53145
"""

from apps.authentication.models import AdminUser

admin_user = AdminUser.objects.filter(role='superadmin').first()

t, created = EmailTemplate.objects.get_or_create(
    name="Internship Selection Notification",
    defaults={
        "subject": "Update on your Internship Application at Exposys Data Labs",
        "body_html": html_content.strip(),
        "body_plain": plain_text.strip(),
        "created_by": admin_user,
    }
)

if not created:
    t.body_html = html_content.strip()
    t.body_plain = plain_text.strip()
    t.save()
    print("Template updated successfully.")
else:
    print("Template created successfully.")
