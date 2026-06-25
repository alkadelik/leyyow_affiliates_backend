from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.db import transaction
from django.utils.timezone import now
from payouts.emails import send_payout_approved, send_payout_paid, send_payout_cancelled
from payouts.models import PayoutRequest


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_confirm_payment(self, conversion_id):
    """
    Call Paystack to verify a payment and confirm or flag the associated commission.

    On success: recalculate commission using Paystack's confirmed amount, mark
    Commission as earned, and credit the affiliate and central wallets.

    On failure: flag the Conversion and leave the Commission as pending.

    Retries up to 3 times (60s apart) on transient errors. If all retries
    are exhausted the conversion is flagged as confirmation_timed_out.
    """
    from tracking.models import Conversion, Commission, CentralWallet
    from accounts.models import AffiliateWallet
    from tracking.central_wallet import credit_central_wallet
    from payouts.paystack import verify_transaction

    try:
        conversion = Conversion.objects.select_related(
            'lead', 'campaign', 'affiliate'
        ).get(id=conversion_id)
    except Conversion.DoesNotExist:
        return

    commission = Commission.objects.filter(
        conversion=conversion, status='pending'
    ).first()
    if not commission:
        return  # already confirmed or no commission expected

    # ── Call Paystack ─────────────────────────────────────────────────────────
    try:
        result = verify_transaction(conversion.payment_id)
    except Exception as exc:
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            _flag_conversion(conversion, 'payment_confirmation_timed_out')
            return

    # ── Unconfirmed ───────────────────────────────────────────────────────────
    if result['status'] != 'success':
        _flag_conversion(conversion, f"payment_{result['status']}")
        return

    # ── Confirmed ─────────────────────────────────────────────────────────────
    confirmed_kobo = result['amount']

    # Recalculate commission amount using the confirmed payment amount and the
    # snapshot of the commission rate that was captured when the event arrived.
    commission_type  = commission.commission_type_snapshot
    commission_value = commission.commission_value_snapshot
    commission_cap   = commission.commission_cap_snapshot

    if commission_type == 'flat_fee':
        confirmed_commission = commission_value
    elif commission_type == 'percentage':
        confirmed_commission = int(confirmed_kobo * commission_value / 10000)
    elif commission_type == 'percentage_capped':
        confirmed_commission = min(int(confirmed_kobo * commission_value / 10000), commission_cap)
    else:
        confirmed_commission = 0

    with transaction.atomic():
        commission.amount         = confirmed_commission
        commission.payment_amount = confirmed_kobo
        commission.status         = 'earned'
        commission.earned_at      = now()
        commission.save(update_fields=['amount', 'payment_amount', 'status', 'earned_at'])

        wallet = AffiliateWallet.objects.select_for_update().get(affiliate=conversion.affiliate)
        wallet.balance      += confirmed_commission
        wallet.total_earned += confirmed_commission
        wallet.save(update_fields=['balance', 'total_earned', 'updated_at'])

        credit_central_wallet(commission)

        if conversion.lead_id:
            from tracking.models import MerchantLead as _Lead
            lead = _Lead.objects.select_for_update().get(id=conversion.lead_id)
            lead.amount_paid_kobo       = confirmed_kobo
            lead.total_amount_paid_kobo = (lead.total_amount_paid_kobo or 0) + confirmed_kobo
            lead.save(update_fields=['amount_paid_kobo', 'total_amount_paid_kobo', 'updated_at'])


def _flag_conversion(conversion, reason):
    conversion.is_flagged = True
    conversion.flag_reason = reason
    conversion.save(update_fields=['is_flagged', 'flag_reason'])


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_payout_approved(self, payout_id):
    try:
        payout = PayoutRequest.objects.get(id=payout_id)
        send_payout_approved(payout)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_payout_paid(self, payout_id):
    try:
        payout = PayoutRequest.objects.get(id=payout_id)
        send_payout_paid(payout)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_payout_cancelled(self, payout_id):
    try:
        payout = PayoutRequest.objects.get(id=payout_id)
        send_payout_cancelled(payout)
    except Exception as exc:
        raise self.retry(exc=exc)
