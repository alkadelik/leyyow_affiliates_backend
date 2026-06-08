"""
Management command: activate_scheduled_campaigns
=================================================
Finds all scheduled campaigns whose starts_at has been reached
and transitions them to active.

Run via cron every minute:
    * * * * * /path/to/python manage.py activate_scheduled_campaigns
"""
from django.core.management.base import BaseCommand
from django.utils.timezone import now
from django.db import transaction
from campaigns.models import Campaign, CampaignAffiliate
from campaigns.task import task_send_campaign_going_live


class Command(BaseCommand):
    help = 'Activate scheduled campaigns whose start date has been reached'

    def handle(self, *args, **options):
        due = Campaign.objects.filter(
            status='scheduled',
            starts_at__lte=now(),
        )

        if not due.exists():
            self.stdout.write('No campaigns to activate.')
            return

        activated = 0
        for campaign in due:
            try:
                with transaction.atomic():
                    campaign.status = 'active'
                    campaign.save(update_fields=['status', 'updated_at'])

                    # Set assigned affiliates to active
                    assigned = CampaignAffiliate.objects.filter(
                        campaign=campaign,
                        removed_at__isnull=True,
                    ).select_related('affiliate')

                    for ca in assigned:
                        ca.affiliate.status = 'active'
                        ca.affiliate.save(update_fields=['status'])
                        try:
                            task_send_campaign_going_live.delay(str(ca.affiliate.id), campaign)
                        except Exception as e:
                            self.stderr.write(
                                f'  Email failed for {ca.affiliate.email}: {e}'
                            )

                activated += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  Activated: {campaign.name} ({campaign.id})')
                )

            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(f'  Failed to activate {campaign.name}: {e}')
                )

        self.stdout.write(self.style.SUCCESS(f'Done. {activated} campaign(s) activated.'))
