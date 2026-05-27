import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Raised when an email cannot be sent."""
    pass


class BrevoEmailProvider:
    """
    Email provider implementation using Brevo (formerly Sendinblue)
    Transactional Email API via sib_api_v3_sdk.
    """

    def __init__(self):
        import sib_api_v3_sdk

        configuration = sib_api_v3_sdk.Configuration()
        api_key = getattr(settings, "BREVO_API_KEY", "")
        configuration.api_key["api-key"] = api_key
        self._api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )
        self._sender_email = getattr(settings, "BREVO_SENDER_EMAIL", "")
        self._sender_name = getattr(settings, "BREVO_SENDER_NAME", "")

    def send_single(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        plain_content: str = '',
    ) -> dict:
        """
        Send a single transactional email via Brevo.

        Args:
            to_email: Recipient email address.
            to_name: Recipient display name.
            subject: Email subject line.
            html_content: HTML body of the email.
            plain_content: Plain-text body of the email (optional).

        Returns:
            Dict with 'message_id' and 'status' on success,
            or 'status' and 'error' on failure.
        """
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{'email': to_email, 'name': to_name}],
            sender={'email': self._sender_email, 'name': self._sender_name},
            subject=subject,
            html_content=html_content,
            text_content=plain_content if plain_content else None,
        )

        try:
            response = self._api_instance.send_transac_email(send_smtp_email)
            logger.info(f'Brevo email sent to {to_email}, message_id={response.message_id}')
            return {
                'message_id': response.message_id,
                'status': 'sent',
            }
        except ApiException as e:
            logger.error(f'Brevo API error sending to {to_email}: {e}')
            return {
                'status': 'failed',
                'error': str(e),
            }


class SESEmailProvider:
    """
    Email provider implementation using Amazon SES via boto3.
    """

    def __init__(self):
        import boto3

        self._client = boto3.client(
            'ses',
            aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            region_name=getattr(settings, 'AWS_REGION', None),
        )
        self._from_email = getattr(settings, 'AWS_SES_FROM_EMAIL', '')

    def send_single(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        plain_content: str = '',
    ) -> dict:
        """
        Send a single email via Amazon SES.

        Args:
            to_email: Recipient email address.
            to_name: Recipient display name.
            subject: Email subject line.
            html_content: HTML body of the email.
            plain_content: Plain-text body of the email (optional).

        Returns:
            Dict with 'message_id' and 'status' on success,
            or 'status' and 'error' on failure.
        """
        from botocore.exceptions import ClientError

        body = {
            'Html': {
                'Data': html_content,
                'Charset': 'UTF-8',
            },
        }
        if plain_content:
            body['Text'] = {
                'Data': plain_content,
                'Charset': 'UTF-8',
            }

        try:
            response = self._client.send_email(
                Source=f'{to_name} <{self._from_email}>'.strip() if to_name else self._from_email,
                Destination={
                    'ToAddresses': [to_email],
                },
                Message={
                    'Subject': {
                        'Data': subject,
                        'Charset': 'UTF-8',
                    },
                    'Body': body,
                },
            )
            message_id = response['MessageId']
            logger.info(f'SES email sent to {to_email}, message_id={message_id}')
            return {
                'message_id': message_id,
                'status': 'sent',
            }
        except ClientError as e:
            logger.error(f'SES error sending to {to_email}: {e}')
            return {
                'status': 'failed',
                'error': str(e),
            }


class EmailService:
    """
    Factory/facade for email sending. Reads EMAIL_PROVIDER from Django settings
    and instantiates the correct provider ('brevo' or 'ses').
    """

    PROVIDERS = {
        'brevo': BrevoEmailProvider,
        'ses': SESEmailProvider,
    }

    def __init__(self):
        provider_name = getattr(settings, 'EMAIL_PROVIDER', 'brevo').lower()
        provider_class = self.PROVIDERS.get(provider_name)
        if provider_class is None:
            raise EmailSendError(
                f"Unsupported email provider: '{provider_name}'. "
                f"Supported providers: {', '.join(self.PROVIDERS.keys())}"
            )
        self._provider = provider_class()

    def send_single(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        plain_content: str = '',
    ) -> dict:
        """
        Delegate sending a single email to the configured provider.

        Args:
            to_email: Recipient email address.
            to_name: Recipient display name.
            subject: Email subject line.
            html_content: HTML body of the email.
            plain_content: Plain-text body of the email (optional).

        Returns:
            Dict with sending result from the provider.
        """
        return self._provider.send_single(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            plain_content=plain_content,
        )


def send_notification(admin_email: str, subject: str, body_html: str):
    """Sends a system notification to the admin. Uses same provider as campaigns."""
    try:
        provider = EmailService()
        provider.send_single(
            to_email=admin_email,
            to_name="Exposys Admin",
            subject=subject,
            html_content=body_html,
            plain_content=body_html
        )
    except Exception as e:
        logger.error(f"Failed to send notification email to {admin_email}: {e}")

