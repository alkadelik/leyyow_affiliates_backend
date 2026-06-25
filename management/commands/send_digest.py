from django.core.management.base import BaseCommand
from django.utils.timezone import now, timedelta
from tracking.models import Commission
from accounts.models import Affiliate
from tracking.emails import send_weekly_digest


class Command(BaseCommand):
    help = 'Send weekly earnings digest emails to all affiliates with earnings in the last 7 days.'

    def handle(self, *args, **options):
        since = now() - timedelta(days=7)

        affiliate_ids = Commission.objects.filter(
            earned_at__gte=since,
            status='earned',
        ).values_list('affiliate_id', flat=True).distinct()

        affiliates = Affiliate.objects.filter(id__in=affiliate_ids, status='active')

        self.stdout.write(f"Sending weekly digest to {affiliates.count()} affiliate(s)...")

        for affiliate in affiliates:
            send_weekly_digest(affiliate)
            self.stdout.write(f"  ✓ Sent to {affiliate.email}")

        self.stdout.write(self.style.SUCCESS('Weekly digest emails sent.'))
