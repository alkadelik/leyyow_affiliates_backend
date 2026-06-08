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


def create_commission(conversion, payment_amount_kobo, external_payment_id=None):
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
            external_payment_id       = external_payment_id,
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
    Returns (is_eligible: bool, commission_amount: int kobo)
    """
    campaign = lead.campaign

    # Tier check
    if campaign.tier and campaign.tier != 'all' and lead.subscription_tier != campaign.tier:
        return False, 0

    trigger = campaign.commission_trigger

    if trigger == 'first_subscription_only':
        from tracking.models import Conversion
        already_converted = Conversion.objects.filter(lead=lead).exists()
        if already_converted:
            return False, 0

    elif trigger == 'subscriptions_within_period':
        cutoff = lead.signed_up_at + timedelta(days=campaign.commission_period_days or 0)
        if occurred_at > cutoff:
            return False, 0

    # trigger == 'all_subscriptions': always eligible, fall through

    amount = _calculate_amount(campaign, amount_paid_kobo)
    return True, amount


def _calculate_amount(campaign, amount_paid_kobo):
    # Per-tier override
    if campaign.commission_per_tier and campaign.tier and campaign.tier != 'all':
        tier_amount = campaign.commission_per_tier.get(campaign.tier)
        if tier_amount is not None:
            return tier_amount

    return calculate_commission(campaign, amount_paid_kobo or 0)