from celery import shared_task
from accounts.models import Affiliate
from campaigns.models import Campaign
from campaigns.emails import send_campaign_invite, send_campaign_going_live_tomorrow, send_campaign_ended_summary


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_campaign_invite(self, affiliate_id, campaign_id):
    try:
        affiliate = Affiliate.objects.get(id=affiliate_id)
        campaign  = Campaign.objects.get(id=campaign_id)
        send_campaign_invite(affiliate, campaign)
    except Exception as exc:
        raise self.retry(exc=exc)
    

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_campaign_going_live(self, campaign_id):
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        send_campaign_going_live_tomorrow(campaign)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_campaign_ended(self, campaign_id):
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        send_campaign_ended_summary(campaign)
    except Exception as exc:
        raise self.retry(exc=exc)