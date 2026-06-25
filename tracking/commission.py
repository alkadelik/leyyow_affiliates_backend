from django.utils.timezone import now
from django.db import transaction
from tracking.models import Commission
from accounts.models import AffiliateWallet
from datetime import timedelta


def calculate_commission(campaign, payment_amount_kobo):
    """
    Calculate commission amount in kobo based on campaign commission structure.

    commission_value for percentage types is stored in basis points:
    1000 basis points = 10%

    Returns integer (kobo).
    """
    commission_type  = campaign.commission_type
    commission_value = campaign.commission_value
    commission_cap   = campaign.commission_cap

    if commission_type == 'flat_fee':
        return commission_value

    if commission_type == 'percentage':
        return int(payment_amount_kobo * commission_value / 10000)

    if commission_type == 'percentage_capped':
        amount = int(payment_amount_kobo * commission_value / 10000)
        return min(amount, commission_cap)

    return 0


def create_commission(conversion, payment_amount_kobo):
    """
    Create a commission record and credit the affiliate wallet and central wallet.
    Everything runs in a single atomic transaction.

    Returns the Commission instance.
    """
    campaign         = conversion.campaign
    affiliate        = conversion.affiliate
    commission_amount = calculate_commission(campaign, payment_amount_kobo)

    with transaction.atomic():
        commission = Commission.objects.create(
            conversion                = conversion,
            affiliate                 = affiliate,
            campaign                  = campaign,
            status                    = 'earned',
            amount                    = commission_amount,
            payment_amount            = payment_amount_kobo,
            commission_type_snapshot  = campaign.commission_type,
            commission_value_snapshot = campaign.commission_value,
            commission_cap_snapshot   = campaign.commission_cap,
            earned_at                 = now(),
        )

        # Credit affiliate wallet
        wallet = AffiliateWallet.objects.select_for_update().get(affiliate=affiliate)
        wallet.balance       += commission_amount
        wallet.total_earned  += commission_amount
        wallet.save(update_fields=['balance', 'total_earned', 'updated_at'])

        # Credit central wallet
        from tracking.central_wallet import credit_central_wallet
        credit_central_wallet(commission)

    return commission


def reverse_commission(commission):
    """
    Reverse an earned commission due to a refund (Decision 4).
    Creates a new reversal commission row and debits the affiliate wallet.
    """
    if commission.status != 'earned':
        raise ValueError('Only earned commissions can be reversed.')

    affiliate = commission.affiliate

    with transaction.atomic():
        # Mark original as reversed
        commission.status      = 'reversed'
        commission.reversed_at = now()
        commission.save(update_fields=['status', 'reversed_at'])

        # Debit affiliate wallet
        wallet = AffiliateWallet.objects.select_for_update().get(affiliate=affiliate)
        wallet.balance      -= commission.amount
        wallet.total_earned -= commission.amount
        wallet.save(update_fields=['balance', 'total_earned', 'updated_at'])

        # Debit central wallet
        from tracking.central_wallet import debit_central_wallet
        debit_central_wallet(commission)

    return commission


def _check_eligibility(lead, occurred_at, amount_paid_kobo):
    """
    Returns (is_eligible: bool, commission_amount: int kobo, snapshot: dict).
    snapshot contains commission_type_snapshot, commission_value_snapshot, commission_cap_snapshot.
    """
    campaign = lead.campaign

    if campaign.campaign_type == 'tiered':
        return _check_tiered_eligibility(lead, amount_paid_kobo)

    # ── Fixed campaign ────────────────────────────────────────────────────────

    # Subscription tier check
    if campaign.tier and campaign.tier != 'all' and lead.subscription_tier != campaign.tier:
        return False, 0, {}

    trigger = campaign.commission_trigger

    if trigger == 'first_subscription_only':
        from tracking.models import Conversion
        already_converted = Conversion.objects.filter(lead=lead).exists()
        if already_converted:
            return False, 0, {}

    elif trigger == 'subscriptions_within_period':
        cutoff = lead.signed_up_at + timedelta(days=campaign.commission_period_days or 0)
        if occurred_at > cutoff:
            return False, 0, {}

    # trigger == 'all_subscriptions': always eligible, fall through

    amount = _calculate_amount(campaign, amount_paid_kobo)
    return True, amount, {
        'commission_type_snapshot':  campaign.commission_type,
        'commission_value_snapshot': campaign.commission_value,
        'commission_cap_snapshot':   campaign.commission_cap,
    }


def _check_tiered_eligibility(lead, amount_paid_kobo):
    """
    Evaluate commission for a tiered campaign.

    Subscriber count is taken AFTER the lead's status has already been updated
    (lead.save() runs before this is called), so the new subscriber is included.
    """
    from tracking.models import MerchantLead

    campaign        = lead.campaign
    subscriber_tiers = campaign.subscriber_tiers or []

    subscriber_count = MerchantLead.objects.filter(
        affiliate=lead.affiliate,
        campaign=campaign,
        status__in=['subscribed', 'renewed'],
    ).count()

    matched_tier = None
    for tier in subscriber_tiers:
        min_s = tier['min_subs']
        max_s = tier.get('max_subs')
        if subscriber_count >= min_s and (max_s is None or subscriber_count <= max_s):
            matched_tier = tier
            break

    if not matched_tier:
        return False, 0, {}

    commission_type  = matched_tier['commission_type']
    commission_value = matched_tier['commission_value']

    if commission_type == 'flat_fee':
        amount = commission_value
    elif commission_type == 'percentage':
        amount = int((amount_paid_kobo or 0) * commission_value / 10000)
    else:
        return False, 0, {}

    return True, amount, {
        'commission_type_snapshot':  commission_type,
        'commission_value_snapshot': commission_value,
        'commission_cap_snapshot':   None,
    }


def _calculate_amount(campaign, amount_paid_kobo):
    # Per-tier override (subscription tier bloom/burst)
    if campaign.commission_per_tier and campaign.tier and campaign.tier != 'all':
        tier_amount = campaign.commission_per_tier.get(campaign.tier)
        if tier_amount is not None:
            return tier_amount

    return calculate_commission(campaign, amount_paid_kobo or 0)
