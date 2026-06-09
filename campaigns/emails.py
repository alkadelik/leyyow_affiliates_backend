"""
campaigns/emails.py

Emails triggered by campaign lifecycle events.
Templates live in: affiliates_backend/templates/emails/
"""
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

from tracking.models import AffiliateLink, AffiliateCode
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


def _commission_display(campaign):
    """Return a human-readable commission string for a campaign."""
    ct = campaign.commission_type
    if ct == 'flat_fee':
        amount = campaign.commission_value // 100
        return f"₦{amount:,} per subscription"
    elif ct == 'percentage':
        pct = campaign.commission_value / 100
        return f"{pct:.0f}% of subscription payment"
    elif ct == 'percentage_capped':
        pct = campaign.commission_value / 100
        cap = campaign.commission_cap // 100
        return f"{pct:.0f}% of payment, capped at ₦{cap:,}"
    return "See campaign details"


def _end_condition_displays(campaign):
    """Return (end_date_display, end_volume_display) — either may be empty string."""
    end_date = ''
    end_volume = ''
    if campaign.ends_at:
        end_date = campaign.ends_at.strftime('%-d %B %Y')
    if campaign.conversion_limit:
        end_volume = f"{campaign.conversion_limit:,} conversions"
    return end_date, end_volume


# ── Campaign invite (to affiliate) ───────────────────────────────────────────

def send_campaign_invite(affiliate, campaign):
    """
    Sent to an affiliate when they are assigned to a campaign that is already
    active, or when an active campaign they are assigned to goes live.
    """
    first_name = affiliate.full_name.split()[0]

    try:
        link = AffiliateLink.objects.get(affiliate=affiliate, campaign=campaign)
        _base = SystemSettings.get().tracking_base_url or getattr(settings, 'TRACKING_BASE_URL', 'https://leyyow.com')
        tracking_url = f"{_base.rstrip('/')}/r/{link.slug}"
    except AffiliateLink.DoesNotExist:
        tracking_url = ''

    try:
        coupon = AffiliateCode.objects.get(affiliate=affiliate, campaign=campaign)
        coupon_code = coupon.code
    except AffiliateCode.DoesNotExist:
        coupon_code = ''

    end_date, end_volume = _end_condition_displays(campaign)
    campaign_url = f"{settings.AFFILIATE_FRONTEND_URL}/campaigns/{campaign.id}"

    _send(
        subject=f"You've been added to a Leyyow campaign — {campaign.name}",
        to_email=affiliate.email,
        template_name='emails/campaign_invite',
        context={
            'first_name':          first_name,
            'campaign_name':       campaign.name,
            'campaign_url':        campaign_url,
            'coupon_code':         coupon_code,
            'tracking_url':        tracking_url,
            'commission_display':  _commission_display(campaign),
            'end_date':            end_date,
            'end_volume':          end_volume,
        },
    )


# ── Campaign going live tomorrow (to Leyyow admin) ───────────────────────────

def send_campaign_going_live_tomorrow(campaign):
    """
    Sent to ADMIN_NOTIFICATION_EMAIL the day before a scheduled campaign starts.
    """
    from campaigns.models import CampaignAffiliate

    affiliate_count = CampaignAffiliate.objects.filter(
        campaign=campaign, removed_at__isnull=True
    ).count()

    end_date, end_volume = _end_condition_displays(campaign)
    campaign_url = f"{settings.ADMIN_FRONTEND_URL}/campaigns/{campaign.id}"

    _send(
        subject=f"Campaign goes live tomorrow — {campaign.name}",
        to_email=settings.ADMIN_NOTIFICATION_EMAIL,
        template_name='emails/campaign_going_live',
        context={
            'campaign_name':       campaign.name,
            'campaign_url':        campaign_url,
            'start_date_display':  campaign.starts_at.strftime('%-d %B %Y') if campaign.starts_at else '',
            'end_date_display':    end_date,
            'end_volume_display':  end_volume,
            'affiliate_count':     affiliate_count,
            'commission_display':  _commission_display(campaign),
        },
    )


# ── Campaign ended summary (to each assigned affiliate) ──────────────────────

def send_campaign_ended_summary(campaign):
    """
    Sent to every active affiliate on the campaign when it transitions to 'ended'.
    """
    from campaigns.models import CampaignAffiliate
    from tracking.models import Commission

    assignments = CampaignAffiliate.objects.filter(
        campaign=campaign, removed_at__isnull=True
    ).select_related('affiliate')

    end_date_display = ''
    if campaign.ends_at:
        end_date_display = campaign.ends_at.strftime('%-d %B %Y')
    elif campaign.ended_at:
        end_date_display = campaign.ended_at.strftime('%-d %B %Y')

    wallet_url = f"{settings.AFFILIATE_FRONTEND_URL}/wallet"

    for assignment in assignments:
        affiliate  = assignment.affiliate
        first_name = affiliate.full_name.split()[0]

        commissions_qs = Commission.objects.filter(
            affiliate=affiliate,
            campaign=campaign,
            status='earned',
        ).order_by('created_at')

        commission_count = commissions_qs.count()
        total_kobo  = sum(c.amount for c in commissions_qs)
        total_naira = total_kobo // 100

        commission_rows = []
        for c in commissions_qs:
            merchant_name = c.conversion.merchant_name or 'Unknown merchant'
            commission_rows.append({
                'merchant_name':  merchant_name,
                'date_display':   c.created_at.strftime('%-d %b'),
                'amount_display': f"₦{(c.amount // 100):,}",
            })

        _send(
            subject=f"Campaign ended — your {campaign.name} summary",
            to_email=affiliate.email,
            template_name='emails/campaign_ended',
            context={
                'first_name':           first_name,
                'campaign_name':        campaign.name,
                'end_date_display':     end_date_display,
                'total_earned_display': f"₦{total_naira:,}",
                'conversion_count':     commission_count,
                'conversion_rate':      '',
                'commissions':          commission_rows,
                'wallet_url':           wallet_url,
            },
        )