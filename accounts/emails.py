"""
accounts/emails.py

Transactional emails for affiliate and admin auth flows.
All functions send multipart (HTML + plain text) emails.
Templates live in: affiliates_backend/templates/emails/
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings


def _send(subject, to_email, template_name, context):
    """
    Helper: render an HTML template + plain-text fallback and send.

    template_name — e.g. 'emails/affiliate_invite'
    Looks for:
      templates/emails/<template_name>.html
      templates/emails/<template_name>.txt
    """
    context.setdefault('recipient_email', to_email)

    html_body = render_to_string(f'{template_name}.html', context)
    text_body = render_to_string(f'{template_name}.txt', context)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.attach_alternative(html_body, 'text/html')
    msg.send()


# ── Affiliate invite ──────────────────────────────────────────────────────────

def send_affiliate_invite(affiliate, activate_url):
    """
    Sent when an admin creates a new affiliate.

    Context:
      first_name   — affiliate's first name
      activate_url — full token URL for account activation
    """
    first_name = affiliate.full_name.split()[0]
    _send(
        subject="You've been invited to join Leyyow Affiliates",
        to_email=affiliate.email,
        template_name='emails/affiliate_invite',
        context={
            'first_name': first_name,
            'activate_url': activate_url,
        },
    )


# ── Affiliate welcome ─────────────────────────────────────────────────────────

def send_affiliate_welcome(affiliate):
    """
    Sent after affiliate successfully completes registration.

    Context:
      first_name    — affiliate's first name
      dashboard_url — affiliate portal dashboard URL
    """
    first_name = affiliate.full_name.split()[0]
    dashboard_url = f"{settings.AFFILIATE_FRONTEND_URL}/dashboard"
    _send(
        subject="Welcome to Leyyow Affiliates — your account is active",
        to_email=affiliate.email,
        template_name='emails/affiliate_welcome',
        context={
            'first_name': first_name,
            'dashboard_url': dashboard_url,
        },
    )


# ── Password reset — affiliate ────────────────────────────────────────────────

def send_affiliate_password_reset(affiliate, reset_url):
    """
    Sent when an affiliate requests a password reset.

    Context:
      first_name — affiliate's first name
      reset_url  — full token URL for password reset
      portal     — 'affiliate'
    """
    first_name = affiliate.full_name.split()[0]
    _send(
        subject="Reset your Leyyow password",
        to_email=affiliate.email,
        template_name='emails/password_reset',
        context={
            'first_name': first_name,
            'reset_url': reset_url,
            'portal': 'affiliate',
        },
    )


# ── Password reset — admin ────────────────────────────────────────────────────

def send_admin_password_reset(admin, reset_url):
    """
    Sent when a Leyyow admin requests a password reset.

    Context:
      first_name — admin's first name
      reset_url  — full token URL for password reset
      portal     — 'admin'
    """
    first_name = admin.full_name.split()[0]
    _send(
        subject="Reset your Leyyow admin password",
        to_email=admin.email,
        template_name='emails/password_reset',
        context={
            'first_name': first_name,
            'reset_url': reset_url,
            'portal': 'admin',
        },
    )
