"""
Management command: end_active_campaigns
=========================================
Finds all active campaigns whose ends_at has passed OR whose
conversion_limit has been reached and transitions them to ended.

Run via cron every minute:
    * * * * * /path/to/python manage.py end_active_campaigns
"""
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from django.db import transaction, models as db_models


class Command(BaseCommand):
    help = 'End active campaigns whose end date or conversion limit has been reached'

    def handle(self, *args, **options):
        from campaigns.models import Campaign, CampaignAffiliate
        from campaigns.task import task_send_campaign_ended
        from tracking.models import MerchantLead

        # Find campaigns past their end date
        date_expired = Campaign.objects.filter(
            status='active',
            ends_at__lte=now(),
        )

        # Find campaigns that hit their conversion limit
        # Annotate with subscribed lead count, filter where it meets or exceeds limit
        limit_reached = Campaign.objects.filter(
            status='active',
            conversion_limit__isnull=False,
        ).annotate(
            subscribed_count=db_models.Count(
                'leads',
                filter=db_models.Q(leads__status='subscribed'),
            )
        ).filter(
            subscribed_count__gte=db_models.F('conversion_limit')
        )

        # Combine — use union of IDs to avoid double-processing
        due_ids = set(
            list(date_expired.values_list('id', flat=True)) +
            list(limit_reached.values_list('id', flat=True))
        )

        if not due_ids:
            self.stdout.write('No campaigns to end.')
            return

        due = Campaign.objects.filter(id__in=due_ids)
        ended = 0

        for campaign in due:
            try:
                with transaction.atomic():
                    campaign.status   = 'ended'
                    campaign.ended_at = now()
                    campaign.save(update_fields=['status', 'ended_at', 'updated_at'])

                    # Update affiliate statuses — set inactive if no other active campaigns
                    assigned = CampaignAffiliate.objects.filter(
                        campaign=campaign,
                        removed_at__isnull=True,
                    ).select_related('affiliate')

                    for ca in assigned:
                        still_active = CampaignAffiliate.objects.filter(
                            affiliate=ca.affiliate,
                            removed_at__isnull=True,
                            campaign__status='active',
                        ).exclude(campaign=campaign).exists()

                        ca.affiliate.status = 'active' if still_active else 'inactive'
                        ca.affiliate.save(update_fields=['status'])

                    # Send summary email
                    try:
                        task_send_campaign_ended.delay(str(campaign.id))
                    except Exception as e:
                        self.stderr.write(
                            f'  Summary email failed for {campaign.name}: {e}'
                        )

                ended += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  Ended: {campaign.name} ({campaign.id})')
                )

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'  Failed to end {campaign.name}: {e}')
                )

        self.stdout.write(self.style.SUCCESS(f'Done. {ended} campaign(s) ended.'))
