"""
Management command: seed_test_data
====================================
Creates:
  - 7 campaigns (mix of commission types, triggers, end conditions)
  - 15 affiliates
  - Each affiliate assigned to 2–4 campaigns
  - 5–30 referrals per affiliate (mix of signed up only + subscribed)
  - 5+ affiliates with total_earned >= 110,000 kobo (₦1,100)

Usage:
    python manage.py seed_test_data
    python manage.py seed_test_data --flush   # wipe seed data first
"""

import random
import string
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


# ─── helpers ──────────────────────────────────────────────────────────────────

def rand_str(n=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

def rand_slug(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def days_ago(n):
    return timezone.now() - timedelta(days=n)

def days_from_now(n):
    return timezone.now() + timedelta(days=n)


FIRST_NAMES = [
    'Amara', 'Tunde', 'Chisom', 'Bola', 'Emeka',
    'Ngozi', 'Seun', 'Ife', 'Kemi', 'Dayo',
    'Uche', 'Tobi', 'Yemi', 'Femi', 'Ada',
]
LAST_NAMES = [
    'Okafor', 'Adeyemi', 'Eze', 'Bello', 'Nwosu',
    'Afolabi', 'Obi', 'Ibrahim', 'Lawal', 'Chukwu',
    'Olawale', 'Adesanya', 'Musa', 'Okeke', 'Salami',
]

BUSINESS_NAMES = [
    'Zara Fabrics', 'Kemi Kitchen', 'Bright Interiors', 'Naija Prints',
    'Lagos Eats', 'Spice Route', 'Green Thumb', 'Tech Savvy Hub',
    'Eko Blends', 'The Tailor Shop', 'Abuja Crafts', 'Mama Cooks',
    'Swift Laundry', 'Bolt Bakery', 'Prime Cuts', 'Urban Threads',
    'Sunrise Spa', 'Delta Fresh', 'Cozy Corner', 'Jade Palace',
    'Ivory Stores', 'Golden Gate', 'Blue Ocean', 'Red Carpet Events',
    'Cedar House', 'Maple Leaf', 'Silk Road', 'Iron Gate',
    'Stone Arch', 'River Bend', 'Sky View', 'North Star',
    'Summit Peak', 'Valley Green', 'Palm Grove',
]

CAMPAIGN_CONFIGS = [
    {
        'name': 'Q3 Growth Push',
        'description': 'Drive new merchant subscriptions for Q3.',
        'commission_type': 'flat_fee',
        'commission_value': 5_000_00,        # ₦500 per conversion
        'commission_cap': None,
        'commission_trigger': 'first_subscription_only',
        'commission_period_days': None,
        'tier': 'starter',
        'starts_at_offset': -30,
        'ends_at_offset': 60,
        'conversion_limit': None,
    },
    {
        'name': 'Bloom Tier Special',
        'description': 'Percentage commission for bloom tier merchants.',
        'commission_type': 'percentage',
        'commission_value': 1000,          # 10% in basis points
        'commission_cap': None,
        'commission_trigger': 'all_subscriptions',
        'commission_period_days': None,
        'tier': 'bloom',
        'starts_at_offset': -20,
        'ends_at_offset': 40,
        'conversion_limit': None,
    },
    {
        'name': 'Black Friday Blitz',
        'description': 'Capped percentage for Black Friday campaign.',
        'commission_type': 'percentage_capped',
        'commission_value': 1500,          # 15%
        'commission_cap': 2_000_00,        # ₦2,000 cap
        'commission_trigger': 'first_subscription_only',
        'commission_period_days': None,
        'tier': None,
        'starts_at_offset': -10,
        'ends_at_offset': 20,
        'conversion_limit': None,
    },
    {
        'name': 'New Year New Merchants',
        'description': 'Flat fee campaign with conversion limit.',
        'commission_type': 'flat_fee',
        'commission_value': 10_000_00,      # ₦1,000 per conversion
        'commission_cap': None,
        'commission_trigger': 'first_subscription_only',
        'commission_period_days': None,
        'tier': 'starter',
        'starts_at_offset': -60,
        'ends_at_offset': 30,
        'conversion_limit': 100,
    },
    {
        'name': 'Recurring Revenue Drive',
        'description': 'Earn on every renewal within 90 days.',
        'commission_type': 'flat_fee',
        'commission_value': 300_00,        # ₦300 per renewal
        'commission_cap': None,
        'commission_trigger': 'subscriptions_within_period',
        'commission_period_days': 90,
        'tier': None,
        'starts_at_offset': -15,
        'ends_at_offset': 75,
        'conversion_limit': None,
    },
    {
        'name': 'Enterprise Tier Push',
        'description': 'High-value flat fee for enterprise merchants.',
        'commission_type': 'flat_fee',
        'commission_value': 50_000_00,      # ₦5,000 per conversion
        'commission_cap': None,
        'commission_trigger': 'first_subscription_only',
        'commission_period_days': None,
        'tier': 'enterprise',
        'starts_at_offset': -5,
        'ends_at_offset': 90,
        'conversion_limit': None,
    },
    {
        'name': 'Mid-Year Milestone',
        'description': 'Percentage capped — all subscriptions.',
        'commission_type': 'percentage_capped',
        'commission_value': 800,           # 8%
        'commission_cap': 1_500_00,        # ₦1,500 cap
        'commission_trigger': 'all_subscriptions',
        'commission_period_days': None,
        'tier': 'bloom',
        'starts_at_offset': -45,
        'ends_at_offset': 45,
        'conversion_limit': None,
    },
]


class Command(BaseCommand):
    help = 'Seed test data: 7 campaigns, 15 affiliates, referrals, commissions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete previously seeded data before creating new data',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from accounts.models import Affiliate, Admin
        from campaigns.models import Campaign, CampaignAffiliate
        from tracking.models import AffiliateLink, AffiliateCode, Conversion, Commission, MerchantLead, LinkClick
        from accounts.models import AffiliateWallet

        if options['flush']:
            self.stdout.write('Flushing seed data...')
            seed_affiliates = Affiliate.objects.filter(email__endswith='@seed.leyyow.test')
            Commission.objects.filter(campaign__name__in=[c['name'] for c in CAMPAIGN_CONFIGS]).delete()
            Conversion.objects.filter(campaign__name__in=[c['name'] for c in CAMPAIGN_CONFIGS]).delete()
            MerchantLead.objects.filter(campaign__name__in=[c['name'] for c in CAMPAIGN_CONFIGS]).delete()
            LinkClick.objects.filter(campaign__name__in=[c['name'] for c in CAMPAIGN_CONFIGS]).delete()
            AffiliateCode.objects.filter(campaign__name__in=[c['name'] for c in CAMPAIGN_CONFIGS]).delete()
            AffiliateLink.objects.filter(campaign__name__in=[c['name'] for c in CAMPAIGN_CONFIGS]).delete()
            CampaignAffiliate.objects.filter(campaign__name__in=[c['name'] for c in CAMPAIGN_CONFIGS]).delete()
            Campaign.objects.filter(name__in=[c['name'] for c in CAMPAIGN_CONFIGS]).delete()
            AffiliateWallet.objects.filter(affiliate__in=seed_affiliates).delete()  # ← before affiliates
            seed_affiliates.delete()
            self.stdout.write(self.style.SUCCESS('Flush complete.'))

        # ── 1. Get or create an admin to use as campaign creator ──────────────
        admin = Admin.objects.filter(is_active=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR('No active admin found. Create one first.'))
            return

        # ── 2. Create 7 campaigns ─────────────────────────────────────────────
        self.stdout.write('Creating campaigns...')
        campaigns = []
        for cfg in CAMPAIGN_CONFIGS:
            camp, created = Campaign.objects.get_or_create(
                name=cfg['name'],
                defaults=dict(
                    description=cfg['description'],
                    status='active',
                    commission_type=cfg['commission_type'],
                    commission_value=cfg['commission_value'],
                    commission_cap=cfg['commission_cap'],
                    commission_trigger=cfg['commission_trigger'],
                    commission_period_days=cfg['commission_period_days'],
                    tier=cfg['tier'] or '',
                    starts_at=days_ago(-cfg['starts_at_offset']),
                    ends_at=days_from_now(cfg['ends_at_offset']),
                    conversion_limit=cfg['conversion_limit'],
                    created_by=admin,
                ),
            )
            campaigns.append(camp)
            self.stdout.write(f'  {"Created" if created else "Exists"}: {camp.name}')

        # ── 3. Create 15 affiliates ───────────────────────────────────────────
        self.stdout.write('Creating affiliates...')
        affiliates = []
        for i in range(15):
            first = FIRST_NAMES[i]
            last  = LAST_NAMES[i]
            email = f'{first.lower()}.{last.lower()}@seed.leyyow.test'
            aff, created = Affiliate.objects.get_or_create(
                email=email,
                defaults=dict(
                    full_name=f'{first} {last}',
                    status='active',
                    created_by=admin,
                ),
            )
            if created:
                aff.set_password('Seed1234!')
                aff.save()
                AffiliateWallet.objects.get_or_create(affiliate=aff)
            affiliates.append(aff)
            self.stdout.write(f'  {"Created" if created else "Exists"}: {aff.full_name} ({aff.email})')

        # ── 4. Assign affiliates to campaigns (2–4 campaigns each) ───────────
        self.stdout.write('Assigning affiliates to campaigns...')
        # First 5 affiliates get all 7 campaigns (ensures high commission volume)
        # Rest get 2–4 random campaigns
        assignments = {}  # affiliate → [CampaignAffiliate]
        for idx, aff in enumerate(affiliates):
            if idx < 5:
                assigned_camps = campaigns
            else:
                n = random.randint(2, 4)
                assigned_camps = random.sample(campaigns, n)

            assignments[aff.id] = []
            for camp in assigned_camps:
                ca, _ = CampaignAffiliate.objects.get_or_create(
                    affiliate=aff,
                    campaign=camp,
                    defaults=dict(
                        assigned_at=days_ago(random.randint(5, 30)),
                        assigned_by=admin,
                    ),
                )

                # Create affiliate link
                link, _ = AffiliateLink.objects.get_or_create(
                    campaign_affiliate=ca,
                    defaults=dict(
                        campaign=camp,
                        affiliate=aff,
                        slug=rand_slug(8),
                        full_url=f'https://leyyow.com/r/{rand_slug(8)}',
                        click_count=0,
                    ),
                )

                # Create affiliate code
                name_prefix = aff.full_name.replace(' ', '')[:5].upper()
                code_str = f'{name_prefix}-{rand_str(4)}'
                # ensure uniqueness
                while AffiliateCode.objects.filter(code=code_str).exists():
                    code_str = f'{name_prefix}-{rand_str(4)}'

                code, _ = AffiliateCode.objects.get_or_create(
                    campaign_affiliate=ca,
                    defaults=dict(
                        campaign=camp,
                        affiliate=aff,
                        code=code_str,
                        is_custom=False,
                        use_count=0,
                    ),
                )

                assignments[aff.id].append((ca, camp, link, code))

        # ── 5. Create merchant leads + conversions + commissions ──────────────
        self.stdout.write('Creating referrals...')

        # Track which affiliates need high earnings (first 5)
        HIGH_EARNER_INDICES = set(range(5))

        business_pool = BUSINESS_NAMES.copy()
        random.shuffle(business_pool)
        biz_counter = 0

        for idx, aff in enumerate(affiliates):
            aff_assignments = assignments[aff.id]
            if not aff_assignments:
                continue

            is_high_earner = idx in HIGH_EARNER_INDICES
            num_referrals  = random.randint(15, 30) if is_high_earner else random.randint(5, 20)

            total_commission = 0

            for r in range(num_referrals):
                # Pick a random campaign assignment for this referral
                ca, camp, link, code = random.choice(aff_assignments)

                merchant_id   = f'seed-merchant-{uuid.uuid4().hex[:12]}'
                merchant_name = business_pool[biz_counter % len(business_pool)]
                biz_counter  += 1

                use_code      = random.random() < 0.4  # 40% code, 60% link
                referred_days_ago = random.randint(1, 60)
                referred_at   = days_ago(referred_days_ago)

                # MerchantLead — every referral
                lead = MerchantLead.objects.create(
                    merchant_id=merchant_id,
                    merchant_name=merchant_name,
                    affiliate_code=code,
                    affiliate=aff,
                    campaign=camp,
                    status='signed_up',
                    signed_up_at=referred_at,
                )

                # Decide if they subscribed
                # High earners: 70% subscribe. Others: 40%
                will_subscribe = random.random() < (0.70 if is_high_earner else 0.40)

                if will_subscribe:
                    lead.status = 'subscribed'
                    lead.subscription_start = referred_at + timedelta(days=random.randint(0, 3))
                    lead.save()

                    attribution = 'affiliate_code' if use_code else 'affiliate_link'
                    sub_id      = f'sub-{uuid.uuid4().hex[:12]}'

                    conversion = Conversion.objects.create(
                        campaign=camp,
                        affiliate=aff,
                        attribution_source=attribution,
                        affiliate_link=None if use_code else link,
                        affiliate_code=code if use_code else None,
                        merchant_subscription_id=sub_id,
                        merchant_id=merchant_id,
                        merchant_name=merchant_name,
                        registration_at=lead.subscription_start,
                        is_self_referral=False,
                    )

                    # Calculate commission amount
                    if camp.commission_type == 'flat_fee':
                        amount = camp.commission_value
                    elif camp.commission_type == 'percentage':
                        payment = random.randint(5_000_00, 50_000_00)
                        amount  = int(payment * camp.commission_value / 10000)
                    elif camp.commission_type == 'percentage_capped':
                        payment = random.randint(5_000_00, 50_000_00)
                        amount  = int(payment * camp.commission_value / 10000)
                        if camp.commission_cap:
                            amount = min(amount, camp.commission_cap)
                    else:
                        amount = camp.commission_value or 0

                    Commission.objects.create(
                        conversion=conversion,
                        affiliate=aff,
                        campaign=camp,
                        status='earned',
                        amount=amount,
                        payment_amount=amount,
                        commission_type_snapshot=camp.commission_type,
                        commission_value_snapshot=camp.commission_value,  # ← add
                        earned_at=lead.subscription_start + timedelta(days=random.randint(30, 120)),
                    )

                    total_commission += amount

                    # For high earners: sometimes add a renewal commission
                    if is_high_earner and camp.commission_trigger in ('all_subscriptions', 'subscriptions_within_period'):
                        renewal_count = random.randint(1, 4)
                        for _ in range(renewal_count):
                            Commission.objects.create(
                                conversion=conversion,
                                affiliate=aff,
                                campaign=camp,
                                status='earned',
                                amount=amount,
                                payment_amount=amount,
                                commission_type_snapshot=camp.commission_type,
                                commission_value_snapshot=camp.commission_value,
                                earned_at=lead.subscription_start + timedelta(days=random.randint(30, 120)),
                            )
                            total_commission += amount
                else:
                    lead.save()

            # Update wallet
            wallet, _ = AffiliateWallet.objects.get_or_create(affiliate=aff)
            wallet.total_earned += total_commission
            wallet.balance      += total_commission
            wallet.save()

            self.stdout.write(
                f'  {aff.full_name}: {num_referrals} referrals, '
                f'₦{total_commission/100:,.0f} earned'
                + (' ★ high earner' if is_high_earner else '')
            )

        # ── 6. Summary ────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 50))
        self.stdout.write(self.style.SUCCESS('Seed complete.'))
        self.stdout.write(f'  Campaigns:  {Campaign.objects.filter(name__in=[c["name"] for c in CAMPAIGN_CONFIGS]).count()}')
        self.stdout.write(f'  Affiliates: {Affiliate.objects.filter(email__endswith="@seed.leyyow.test").count()}')
        self.stdout.write(f'  Leads:      {MerchantLead.objects.filter(campaign__name__in=[c["name"] for c in CAMPAIGN_CONFIGS]).count()}')
        self.stdout.write(f'  Conversions:{Conversion.objects.filter(campaign__name__in=[c["name"] for c in CAMPAIGN_CONFIGS]).count()}')
        self.stdout.write(f'  Commissions:{Commission.objects.filter(campaign__name__in=[c["name"] for c in CAMPAIGN_CONFIGS]).count()}')

        high_earners = AffiliateWallet.objects.filter(
            affiliate__email__endswith='@seed.leyyow.test',
            total_earned__gte=11_000_000,
        ).count()
        self.stdout.write(f'  Affiliates with ≥₦1,100 earned: {high_earners}')
        self.stdout.write(self.style.SUCCESS('═' * 50))