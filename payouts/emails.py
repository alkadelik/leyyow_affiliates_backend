"""
payouts/emails.py

Payout status notification emails.
Triggered from payouts/views.py on approve, mark_paid, and cancel actions.
Templates live in: affiliates_backend/templates/emails/
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

TRANSFER_FEE_KOBO = 10_000   # ₦100 in kobo (Decision 10)


def _send(subject, to_email, template_name, context):
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


def _build_payout_context(payout_request, status):
    """
    Build the shared context dict for payout_status.html from a PayoutRequest instance.
    """
    affiliate = payout_request.affiliate
    bank_account = payout_request.bank_account

    gross_kobo = payout_request.requested_amount # already stored with fee deducted on request
    # gross = amount requested before fee; net = gross - fee
    # The fee was deducted at request time, so:
    #   payout_request.amount = gross
    #   net = gross - TRANSFER_FEE_KOBO
    # Recalculate for display:
    net_kobo = gross_kobo - TRANSFER_FEE_KOBO

    date_display = ''
    if payout_request.paid_at:
        date_display = payout_request.paid_at.strftime('%-d %b %Y')
    elif payout_request.reviewed_at:
        date_display = payout_request.reviewed_at.strftime('%-d %b %Y')
    elif payout_request.created_at:
        date_display = payout_request.created_at.strftime('%-d %b %Y')

    return {
        'first_name': affiliate.full_name.split()[0],
        'status': status,
        'gross_amount_display': f"₦{(gross_kobo // 100):,}",
        'fee_display': f"₦{(TRANSFER_FEE_KOBO // 100):,}",
        'net_amount_display': f"₦{(net_kobo // 100):,}",
        'bank_name': bank_account.bank_name if bank_account else '',
        'account_last4': (bank_account.account_number[-4:] if bank_account else ''),
        'date_display': date_display,
        'payout_url': f"{settings.AFFILIATE_FRONTEND_URL}/payouts",
    }


# ── Payout approved ───────────────────────────────────────────────────────────

def send_payout_approved(payout_request):
    """
    Sent to affiliate when a Leyyow admin approves their payout request.
    Call from: admin payout approve view.
    """
    context = _build_payout_context(payout_request, status='approved')
    _send(
        subject="Your Leyyow payout request has been approved",
        to_email=payout_request.affiliate.email,
        template_name='emails/payout_status',
        context=context,
    )


# ── Payout paid ───────────────────────────────────────────────────────────────

def send_payout_paid(payout_request):
    """
    Sent to affiliate when a Leyyow admin marks the payout as paid.
    Call from: admin payout mark_paid view.
    """
    context = _build_payout_context(payout_request, status='paid')
    gross_display = context['gross_amount_display']
    _send(
        subject=f"Your Leyyow payout has been paid — {gross_display}",
        to_email=payout_request.affiliate.email,
        template_name='emails/payout_status',
        context=context,
    )


# ── Payout cancelled ──────────────────────────────────────────────────────────

def send_payout_cancelled(payout_request):
    """
    Sent to affiliate when a Leyyow admin cancels a payout request.
    The wallet refund happens in the view before this is called.
    Call from: admin payout cancel view.
    """
    context = _build_payout_context(payout_request, status='cancelled')
    _send(
        subject="Your Leyyow payout request has been cancelled",
        to_email=payout_request.affiliate.email,
        template_name='emails/payout_status',
        context=context,
    )
