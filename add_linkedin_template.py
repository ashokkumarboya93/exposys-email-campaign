import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.templates_engine.models import EmailTemplate
from apps.authentication.models import AdminUser

def seed_template():
    # Find the superadmin user (or any active user) to be the creator
    user = AdminUser.objects.filter(is_active=True).first()
    if not user:
        print("No active user found to assign as template creator.")
        return

    subject = "Your Application Shortlisted for internship Program"
    
    html_content = """<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Exposys Data Labs Internship</title>

</head>



<body style="margin:0; padding:20px 10px; background:#f2f2f2; font-family:Arial, Helvetica, sans-serif; color:#333333;">



<table width="100%" cellpadding="0" cellspacing="0" border="0">

<tr>

<td align="center">



<table width="720" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border:1px solid #dddddd;">



    <!-- Banner -->

    <tr>

        <td style="padding:0; margin:0; line-height:0; font-size:0; overflow:hidden;">



            <img

                src="https://media.licdn.com/dms/image/v2/C511BAQFT-1b2L0yUXA/company-background_10000/company-background_10000/0/1584482377951/upchat_technologies_cover?e=1780318800&v=beta&t=HuTxvBXlD93CO7Iip2Kb9AGKog4xuCw0I9D8RDU1trU"

                alt="Exposys Data Labs Banner"

                width="720"

                style="

                    width:100%;

                    max-width:720px;

                    height:auto;

                    display:block;

                    border:0;

                    margin:0;

                    padding:0;

                ">

        </td>

    </tr>



    <!-- Content -->

    <tr>

        <td style="padding:20px 45px 35px 45px; font-size:15px; line-height:1.9; color:#333333;">



            <p style="margin-top:0;">

                Dear <strong>{{name}}</strong>,

            </p>



            <p>

                Thank you for applying for the internship at

                <strong>Exposys Data Labs</strong>.

            </p>



            <p>

                We are pleased to inform you that, based on our

                <strong>selection criteria</strong>, your profile has been

                shortlisted for a

                <strong>one-month internship opportunity</strong>.

            </p>



            <p>

                🎉 We congratulate you on being shortlisted and look

                forward to welcoming you onboard.

            </p>



            <p>

                After the initial internship period, your performance

                will be evaluated, and successful candidates may

                proceed to the next stage of opportunities.

            </p>



            <p>

                To confirm your participation, a

                <strong>one-time application fee of ₹999/month</strong>

                is applicable.

            </p>



            <p style="margin-bottom:8px;">

                <strong>📌 Internship Benefits:</strong>

            </p>



            <table cellpadding="0" cellspacing="0" border="0" style="line-height:2;">

                <tr>

                    <td>✅</td>

                    <td style="padding-left:10px;">Project Access</td>

                </tr>



                <tr>

                    <td>✅</td>

                    <td style="padding-left:10px;">Technical Support</td>

                </tr>



                <tr>

                    <td>✅</td>

                    <td style="padding-left:10px;">Resume Building Guidance</td>

                </tr>



                <tr>

                    <td>✅</td>

                    <td style="padding-left:10px;">Internship E-Certificate</td>

                </tr>



                <tr>

                    <td>✅</td>

                    <td style="padding-left:10px;">

                        Flexible Timings & Work From Home

                    </td>

                </tr>

            </table>



            <br>



            <p>

                <strong>👉 Apply Online:</strong><br>



                <a href="http://exposysdata.in/registration.php"

                   style="color:#0b57d0; text-decoration:none;">

                    http://exposysdata.in/registration.php

                </a>

            </p>



            <p>

                <strong>📅 Last Date to Apply:</strong> 25.05.2026

            </p>



            <p>

                For any queries, feel free to reach out to us.

            </p>



            <br>



            <p style="margin-bottom:0;">

                Best Regards,

            </p>



            <p style="margin-top:5px;">

                <strong>Team Exposys Data Labs</strong>

            </p>



        </td>

    </tr>



    <!-- Footer -->

    <tr>

        <td style="border-top:1px solid #dddddd; padding:20px 45px; font-size:13px; color:#666666; line-height:1.9;">



            🌐

            <a href="https://www.exposysdata.com"

               style="color:#0b57d0; text-decoration:none;">

                www.exposysdata.com

            </a>



            &nbsp; | &nbsp;



            <a href="https://www.exposysdata.in"

               style="color:#0b57d0; text-decoration:none;">

                www.exposysdata.in

            </a>



            <br>



            📞 +91 77952 07065 / +91 78920 53145



            <br>



            📧 info@exposysdata.com



        </td>

    </tr>



</table>



</td>

</tr>

</table>



</body>

</html>"""

    template = EmailTemplate.objects.create(
        name="Exposys Internship with LinkedIn Banner",
        subject=subject,
        body_html=html_content,
        body_plain="Dear {{name}},\n\nYour profile has been shortlisted for the Exposys Data Labs internship.",
        created_by=user,
        is_active=True
    )

    print(f"Template successfully created with ID: {template.id}")

if __name__ == "__main__":
    seed_template()
