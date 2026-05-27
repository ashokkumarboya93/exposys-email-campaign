import uuid

import jinja2
from jinja2.sandbox import SandboxedEnvironment
from jinja2.exceptions import TemplateSyntaxError, UndefinedError


class TemplateRenderError(Exception):
    """Raised when a template cannot be rendered."""
    pass


class TemplateRenderer:
    """
    Service for rendering email templates using Jinja2's SandboxedEnvironment.

    Provides both raw template rendering and a preview method that pulls
    template and contact data from the database.
    """

    def __init__(self):
        self._env = SandboxedEnvironment(
            autoescape=True,
            undefined=jinja2.Undefined,  # gracefully handle missing vars
        )

    def render(self, template_body: str, context: dict) -> str:
        """
        Render a Jinja2 template string with the given context dict.

        Args:
            template_body: The Jinja2 template string.
            context: Dict of variables to inject into the template.

        Returns:
            The rendered string.

        Raises:
            TemplateRenderError: If rendering fails for any reason.
        """
        try:
            template = self._env.from_string(template_body)
            return template.render(**context)
        except (TemplateSyntaxError, UndefinedError) as e:
            raise TemplateRenderError(f'Template rendering failed: {str(e)}') from e
        except Exception as e:
            raise TemplateRenderError(f'Unexpected template error: {str(e)}') from e

    def preview(self, template_id: str, contact_id: str) -> dict:
        """
        Preview a rendered email for a specific template and contact.

        Fetches the EmailTemplate and Contact from the database, builds a
        context dict from the contact's fields, and renders subject, body_html,
        and body_plain.

        Args:
            template_id: UUID string of the EmailTemplate.
            contact_id: UUID string of the Contact.

        Returns:
            Dict with keys 'subject', 'body_html', 'body_plain' containing
            the rendered content.

        Raises:
            TemplateRenderError: If the template or contact is not found,
                                 or if rendering fails.
        """
        from apps.templates_engine.models import EmailTemplate
        from apps.contacts.models import Contact

        try:
            template = EmailTemplate.objects.get(id=uuid.UUID(template_id))
        except EmailTemplate.DoesNotExist:
            raise TemplateRenderError(f'Template {template_id} not found')

        try:
            contact = Contact.objects.get(id=uuid.UUID(contact_id))
        except Contact.DoesNotExist:
            raise TemplateRenderError(f'Contact {contact_id} not found')

        # Build context from contact fields
        context = {
            'name': contact.name or '',
            'email': contact.email or '',
            'phone': contact.phone or '',
            'college': contact.college or '',
        }
        # Merge any extra fields stored as JSON on the contact
        if contact.extra_fields:
            context.update(contact.extra_fields)

        rendered_subject = self.render(template.subject, context)
        rendered_body_html = self.render(template.body_html, context)
        rendered_body_plain = self.render(template.body_plain, context) if template.body_plain else ''

        return {
            'subject': rendered_subject,
            'body_html': rendered_body_html,
            'body_plain': rendered_body_plain,
        }
