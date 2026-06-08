"""
tracking/emails.py

Daily digest email for affiliates.
Called by: python manage.py send_digest
Templates live in: affiliates_backend/templates/emails/
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

from tracking.models import Commission, AffiliateWallet

PAYOUT_THRESHOLD_KOBO = 5_000_000   # ₦50,000 in kobo (Decision 5)


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


def send_daily_digest(affiliate):
    """
    Send a daily digest to a single affiliate.
    Only called when there is at least one confirmed commission today.
    The management command filters to affiliates with activity before calling this.

    Aggregates:
      - All confirmed commissions earned today (local date)
      - Current wallet balance
      - Distance to payout threshold
    """
    today = timezone.localdate()

    commissions_today = Commission.objects.filter(
        affiliate=affiliate,
        status='confirmed',
        created_at__date=today,
    ).select_related('conversion__merchant', 'campaign').order_by('created_at')

    commission_count = commissions_today.count()
    if commission_count == 0:
        return  # Nothing to send — guard in case called directly

    total_today_kobo = sum(c.amount for c in commissions_today)

    # Wallet balance
    try:
        wallet = AffiliateWallet.objects.get(affiliate=affiliate)
        balance_kobo = wallet.balance
    except AffiliateWallet.DoesNotExist:
        balance_kobo = 0

    remaining_kobo = max(0, PAYOUT_THRESHOLD_KOBO - balance_kobo)
    above_threshold = balance_kobo >= PAYOUT_THRESHOLD_KOBO

    commission_rows = []
    for c in commissions_today:
        merchant_name = getattr(
            getattr(c.conversion, 'merchant', None), 'business_name', 'Unknown merchant'
        )
        campaign_name = c.campaign.name if c.campaign else ''
        commission_rows.append({
            'merchant_name': merchant_name,
            'campaign_name': campaign_name,
            'amount_display': f"₦{(c.amount // 100):,}",
        })

    # Date display
    day_names = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    digest_date_display = (
        f"{day_names[today.weekday()]}, "
        f"{today.strftime('%-d %B %Y')}"
    )

    earnings_url = f"{settings.AFFILIATE_FRONTEND_URL}/analytics"

    first_name = affiliate.full_name.split()[0]

    _send(
        subject=f"Your Leyyow earnings update — {digest_date_display}",
        to_email=affiliate.email,
        template_name='emails/daily_digest',
        context={
            'first_name': first_name,
            'digest_date_display': digest_date_display,
            'commission_count': commission_count,
            'earned_today_display': f"₦{(total_today_kobo // 100):,}",
            'commissions': commission_rows,
            'wallet_balance_display': f"₦{(balance_kobo // 100):,}",
            'payout_threshold_display': f"₦{(PAYOUT_THRESHOLD_KOBO // 100):,}",
            'remaining_display': f"₦{(remaining_kobo // 100):,}",
            'above_threshold': above_threshold,
            'earnings_url': earnings_url,
        },
    )
