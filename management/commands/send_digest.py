from django.core.management.base import BaseCommand
from django.utils.timezone import now, timedelta
from tracking.models import Commission
from accounts.models import Affiliate
from tracking.emails import send_conversion_digest


class Command(BaseCommand):
    help = 'Send daily conversion digest emails to all affiliates with earnings in the last 24 hours.'

    def handle(self, *args, **options):
        since = now() - timedelta(hours=24)

        # Find all affiliates who earned a commission in the last 24 hours
        affiliate_ids = Commission.objects.filter(
            earned_at__gte = since,
            status         = 'earned',
        ).values_list('affiliate_id', flat=True).distinct()

        affiliates = Affiliate.objects.filter(id__in=affiliate_ids, status='active')

        self.stdout.write(f"Sending digest to {affiliates.count()} affiliate(s)...")

        for affiliate in affiliates:
            commissions = Commission.objects.filter(
                affiliate  = affiliate,
                earned_at__gte = since,
                status     = 'earned',
            ).select_related('campaign', 'conversion')

            conversions = [
                {
                    'merchant_name':     c.conversion.merchant_name,
                    'campaign_name':     c.campaign.name,
                    'commission_amount': c.amount,
                }
                for c in commissions
            ]

            send_conversion_digest(affiliate, conversions)
            self.stdout.write(f"  ✓ Sent to {affiliate.email}")

        self.stdout.write(self.style.SUCCESS('Digest emails sent.'))