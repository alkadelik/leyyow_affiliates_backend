from celery import shared_task
from payouts.emails import send_payout_approved, send_payout_paid, send_payout_cancelled
from payouts.models import PayoutRequest


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