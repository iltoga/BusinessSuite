"""
FILE_ROLE: Deadline message builders for the notifications app.

KEY_COMPONENTS:
- build_customer_deadline_notification_payload: Module symbol.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for app routing, model behavior, and service boundaries.
"""

from django.template.loader import render_to_string


def build_customer_deadline_notification_payload(application, task, due_date):
    """Render channel-specific reminder content for a due-tomorrow notification."""
    context = {
        "application": application,
        "customer": application.customer,
        "product": application.product,
        "task": task,
        "due_date": due_date,
        "due_date_display": due_date.strftime("%d-%m-%Y"),
        "notes": application.notes or "-",
    }

    subject = render_to_string("notifications/email/customer_deadline_subject.txt", context).strip()
    email_text = render_to_string("notifications/email/customer_deadline_body.txt", context).strip()
    email_html = render_to_string("notifications/email/customer_deadline_body.html", context).strip()
    whatsapp_text = render_to_string("notifications/whatsapp/customer_deadline.txt", context).strip()

    return {
        "subject": subject,
        "email_text": email_text,
        "email_html": email_html,
        "whatsapp_text": whatsapp_text,
    }
