"""
tracking/emails.py

Weekly affiliate digest. Sent by the send_digest management command.
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from tracking.models import Commission, MerchantLead, AffiliateWallet
from accounts.models import SystemSettings


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


def send_weekly_digest(affiliate):
    """
    Send a weekly activity digest to a single affiliate.
    Only called when there is at least one activity item this week.
    """
    since = timezone.now() - timedelta(days=7)

    new_signups = MerchantLead.objects.filter(
        affiliate=affiliate,
        signed_up_at__gte=since,
    ).count()

    commissions_this_week = Commission.objects.filter(
        affiliate=affiliate,
        status='earned',
        earned_at__gte=since,
    ).select_related('conversion', 'campaign').order_by('earned_at')

    reversals_this_week = Commission.objects.filter(
        affiliate=affiliate,
        status='reversed',
        reversed_at__gte=since,
    ).select_related('conversion', 'campaign').order_by('reversed_at')

    commission_count  = commissions_this_week.count()
    reversal_count    = reversals_this_week.count()

    if new_signups == 0 and commission_count == 0 and reversal_count == 0:
        return

    total_earned_kobo   = sum(c.amount for c in commissions_this_week)
    total_reversed_kobo = sum(c.amount for c in reversals_this_week)

    try:
        wallet = AffiliateWallet.objects.get(affiliate=affiliate)
        balance_kobo = wallet.balance
    except AffiliateWallet.DoesNotExist:
        balance_kobo = 0

    payout_threshold_kobo = SystemSettings.get().minimum_withdrawal_kobo
    remaining_kobo        = max(0, payout_threshold_kobo - balance_kobo)
    above_threshold       = balance_kobo >= payout_threshold_kobo

    commission_rows = [
        {
            'merchant_name': getattr(c.conversion, 'merchant_name', None) or 'Unknown merchant',
            'campaign_name': c.campaign.name if c.campaign else '',
            'amount_display': f"₦{(c.amount // 100):,}",
        }
        for c in commissions_this_week
    ]

    reversal_rows = [
        {
            'merchant_name': getattr(c.conversion, 'merchant_name', None) or 'Unknown merchant',
            'campaign_name': c.campaign.name if c.campaign else '',
            'amount_display': f"₦{(c.amount // 100):,}",
        }
        for c in reversals_this_week
    ]

    today = timezone.localdate()
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    week_end_display = (
        f"{day_names[today.weekday()]}, "
        f"{today.strftime('%-d %B %Y')}"
    )

    first_name = affiliate.full_name.split()[0]

    _send(
        subject=f"Your Leyyow weekly update — {week_end_display}",
        to_email=affiliate.email,
        template_name='emails/weekly_digest',
        context={
            'first_name':               first_name,
            'week_end_display':         week_end_display,
            'new_signups':              new_signups,
            'commission_count':         commission_count,
            'reversal_count':           reversal_count,
            'earned_this_week_display': f"₦{(total_earned_kobo // 100):,}",
            'reversed_this_week_display': f"₦{(total_reversed_kobo // 100):,}",
            'commissions':              commission_rows,
            'reversals':                reversal_rows,
            'wallet_balance_display':   f"₦{(balance_kobo // 100):,}",
            'payout_threshold_display': f"₦{(payout_threshold_kobo // 100):,}",
            'remaining_display':        f"₦{(remaining_kobo // 100):,}",
            'above_threshold':          above_threshold,
            'earnings_url':             f"{settings.AFFILIATE_FRONTEND_URL}/analytics",
        },
    )
