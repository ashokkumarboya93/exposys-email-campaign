import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.templates_engine.models import EmailTemplate
from apps.authentication.models import AdminUser

user = AdminUser.objects.first()
if user:
    subject = 'Shortlisted for internship Program'
    body_html = '''Dear {{first_name}},<br><br>
Thank you for applying for the internship at Exposys Data Labs.<br><br>
We are pleased to inform you that, based on our percentage criteria, your profile has been shortlisted for a one-month internship opportunity.<br><br>
After the initial internship period, your performance will be evaluated, and successful candidates will proceed to the next level of the interview process for extended roles.<br><br>
To confirm your participation, a one-time application fee of ₹999/month is applicable.<br><br>
This includes:<br>
✅ Project Access<br>
✅ Technical Support<br>
✅ Resume Building Guidance<br>
✅ Internship E-Certificate<br>
✅ Flexible Timings & Work From Home<br><br>
👉 Apply Online:<br>
<a href="http://exposysdata.in/registration.php">http://exposysdata.in/registration.php</a><br><br>
📅 Last Date to Apply: 25.05.2026<br><br>
For any queries, feel free to reach out to us.<br><br>
Warm Regards,<br>
Team Exposys Data Labs<br>
🌐 www.exposysdata.com | www.exposysdata.in<br>
📞 +91 77952 07065 / +91 78920 53145'''

    template, created = EmailTemplate.objects.get_or_create(
        name='Shortlisted for Internship',
        defaults={'subject': subject, 'body_html': body_html, 'created_by': user}
    )
    if not created:
        template.subject = subject
        template.body_html = body_html
        template.save()
    print('Template seeded successfully!')
