import json
from django.utils.timezone import now
from payouts.models import PayoutRequest, BankAccount
from accounts.models import AffiliateWallet
from tracking.models import CentralWallet
from payouts.paystack import verify_webhook
from payouts.task import task_send_payout_paid, task_send_payout_cancelled
from audit.utils import log_action
from django.db import transaction



def handle_paystack_webhook(request):
    """
    Process incoming Paystack webhook events.
    Called from the webhook view after signature verification.
    """
    payload_bytes = request.body
    signature     = request.headers.get('X-Paystack-Signature', '')

    if not verify_webhook(payload_bytes, signature):
        return False, 'Invalid signature'

    try:
        event = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return False, 'Invalid JSON'

    event_type = event.get('event')
    data       = event.get('data', {})

    if event_type == 'transfer.success':
        _handle_transfer_success(data)
    elif event_type in ('transfer.failed', 'transfer.reversed'):
        _handle_transfer_failure(data)

    return True, 'OK'


def _handle_transfer_success(data):
    transfer_code = data.get('transfer_code')
    if not transfer_code:
        return

    try:
        payout = PayoutRequest.objects.select_related(
            'affiliate', 'bank_account'
        ).get(paystack_transfer_code=transfer_code)
    except PayoutRequest.DoesNotExist:
        return

    if payout.status == 'paid':
        return

    with transaction.atomic():
        # Affiliate wallet already debited at request time — no change needed here

        payout.status  = 'paid'
        payout.paid_at = now()
        payout.save(update_fields=['status', 'paid_at'])

        # Update central wallet balance and write ledger event
        from tracking.central_wallet import record_payout_event
        record_payout_event(payout)

    log_action(
        actor_type='system', action='payout.paid',
        entity_type='payout_request', entity_id=payout.id,
    )

    task_send_payout_paid.delay(str(payout.id))


def _handle_transfer_failure(data):
    transfer_code  = data.get('transfer_code')
    failure_reason = data.get('reason', 'Transfer failed')
    if not transfer_code:
        return

    try:
        payout = PayoutRequest.objects.select_related('affiliate').get(
            paystack_transfer_code=transfer_code
        )
    except PayoutRequest.DoesNotExist:
        return

    if payout.status in ('cancelled', 'failed'):
        return

    with transaction.atomic():
        wallet = AffiliateWallet.objects.select_for_update().get(affiliate=payout.affiliate)
        wallet.balance += payout.requested_amount
        wallet.save(update_fields=['balance'])

        payout.status         = 'cancelled'
        payout.failure_reason = failure_reason
        payout.save(update_fields=['status', 'failure_reason'])

    log_action(
        actor_type='system', action='payout.failed',
        entity_type='payout_request', entity_id=payout.id,
        metadata={'reason': failure_reason},
    )

    task_send_payout_cancelled.delay(str(payout.id))