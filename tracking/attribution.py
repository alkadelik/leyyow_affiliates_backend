import hashlib
from django.utils.timezone import now, timedelta
from tracking.models import AffiliateLink, AffiliateCode, LinkClick


ATTRIBUTION_WINDOW_DAYS = 30


def generate_slug(length=8):
    """Generate a unique random URL-safe slug."""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    while True:
        slug = ''.join(secrets.choice(alphabet) for _ in range(length))
        if not AffiliateLink.objects.filter(slug=slug).exists():
            return slug


def generate_code(affiliate):
    """
    Auto-generate a coupon code: first 5 chars of name + hyphen + 4 random chars.
    e.g. AMARA-X7K2. Guaranteed unique.
    """
    import secrets
    import string
    prefix = affiliate.full_name[:5].upper().replace(' ', '')
    alphabet = string.ascii_uppercase + string.digits
    while True:
        suffix = ''.join(secrets.choice(alphabet) for _ in range(4))
        code = f"{prefix}-{suffix}"
        if not AffiliateCode.objects.filter(code=code).exists():
            return code


def get_session_fingerprint(request):
    """
    Build a session fingerprint from IP + user agent.
    Hashed for privacy.
    """
    ip         = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    raw        = f"{ip}:{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def is_duplicate_click(affiliate_link, session_fingerprint):
    """
    Returns True if the same fingerprint clicked the same link within 24 hours.
    """
    if not session_fingerprint:
        return False
    cutoff = now() - timedelta(hours=24)
    return LinkClick.objects.filter(
        affiliate_link=affiliate_link,
        session_fingerprint=session_fingerprint,
        clicked_at__gte=cutoff,
        is_duplicate=False,
    ).exists()


def record_click(request, affiliate_link):
    """
    Record a link click. Marks as duplicate if same fingerprint within 24h.
    Returns the LinkClick instance.
    """
    fingerprint  = get_session_fingerprint(request)
    ip           = get_client_ip(request)
    user_agent   = request.META.get('HTTP_USER_AGENT', '')
    referrer     = request.META.get('HTTP_REFERER', '')
    duplicate    = is_duplicate_click(affiliate_link, fingerprint)

    click = LinkClick.objects.create(
        affiliate_link      = affiliate_link,
        campaign            = affiliate_link.campaign,
        affiliate           = affiliate_link.affiliate,
        clicked_at          = now(),
        ip_address          = ip,
        user_agent          = user_agent,
        referrer_url        = referrer,
        session_fingerprint = fingerprint,
        is_duplicate        = duplicate,
    )

    if not duplicate:
        affiliate_link.click_count += 1
        affiliate_link.save(update_fields=['click_count'])

    return click


def resolve_attribution(merchant_subscription_id, coupon_code=None, session_fingerprint=None):
    """
    Resolve attribution for a subscription registration.

    Priority (Decision 1):
      1. Coupon code — always wins if present and valid
      2. Tracking link — last click within 30-day window
      3. Unattributed

    Returns dict: {
        'source':    'coupon_code' | 'tracking_link' | 'unattributed',
        'affiliate': Affiliate instance or None,
        'campaign':  Campaign instance or None,
        'link':      AffiliateLink or None,
        'code':      AffiliateCode or None,
    }
    """
    # 1. Coupon code takes priority
    if coupon_code:
        try:
            affiliate_code = AffiliateCode.objects.select_related(
                'affiliate', 'campaign'
            ).get(code=coupon_code.upper())

            # Check campaign is still active
            if affiliate_code.campaign.status != 'active':
                pass  # Fall through to link attribution
            else:
                # Self-referral check
                is_self_referral = False  # Resolved in conversion creation

                return {
                    'source':    'coupon_code',
                    'affiliate': affiliate_code.affiliate,
                    'campaign':  affiliate_code.campaign,
                    'link':      None,
                    'code':      affiliate_code,
                }
        except AffiliateCode.DoesNotExist:
            pass  # Fall through to link attribution

    # 2. Tracking link — last click within window
    if session_fingerprint:
        cutoff = now() - timedelta(days=ATTRIBUTION_WINDOW_DAYS)
        click  = LinkClick.objects.filter(
            session_fingerprint = session_fingerprint,
            clicked_at__gte     = cutoff,
            is_duplicate        = False,
            affiliate_link__campaign__status = 'active',
        ).order_by('-clicked_at').first()

        if click:
            return {
                'source':    'tracking_link',
                'affiliate': click.affiliate,
                'campaign':  click.campaign,
                'link':      click.affiliate_link,
                'code':      None,
            }

    # 3. Unattributed
    return {
        'source':    'unattributed',
        'affiliate': None,
        'campaign':  None,
        'link':      None,
        'code':      None,
    }