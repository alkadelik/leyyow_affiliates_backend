from celery import shared_task
from accounts.models import Affiliate
from accounts.emails import send_affiliate_invite, send_affiliate_welcome#, send_password_reset


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_affiliate_invite(self, affiliate_id, invite_url):
    try:
        affiliate = Affiliate.objects.get(id=affiliate_id)
        send_affiliate_invite(affiliate, invite_url)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_affiliate_welcome(self, affiliate_id):
    try:
        affiliate = Affiliate.objects.get(id=affiliate_id)
        send_affiliate_welcome(affiliate)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_password_reset(self, affiliate_id, reset_url):
    try:
        affiliate = Affiliate.objects.get(id=affiliate_id)
        send_password_reset(affiliate, reset_url)
    except Exception as exc:
        raise self.retry(exc=exc)