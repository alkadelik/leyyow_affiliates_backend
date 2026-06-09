from django.db import models

# Create your models here.
import uuid
from django.db import models


class AffiliateLink(models.Model):
    id                   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign_affiliate   = models.OneToOneField(
        'campaigns.CampaignAffiliate',
        on_delete=models.RESTRICT,
        related_name='link'
    )
    campaign             = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.RESTRICT,
        related_name='links'
    )
    affiliate            = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.RESTRICT,
        related_name='links'
    )
    slug                 = models.CharField(max_length=32, unique=True)
    full_url             = models.CharField(max_length=512)
    click_count          = models.IntegerField(default=0)
    created_at           = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'affiliate_links'


class AffiliateCode(models.Model):
    id                 = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign_affiliate = models.OneToOneField(
        'campaigns.CampaignAffiliate',
        on_delete=models.RESTRICT,
        related_name='code'
    )
    campaign           = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.RESTRICT,
        related_name='codes'
    )
    affiliate          = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.RESTRICT,
        related_name='codes'
    )
    code               = models.CharField(max_length=32, unique=True)
    is_custom          = models.BooleanField(default=False)
    use_count          = models.IntegerField(default=0)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'affiliate_codes'


class LinkClick(models.Model):
    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affiliate_link      = models.ForeignKey(
        AffiliateLink,
        on_delete=models.RESTRICT,
        related_name='clicks'
    )
    campaign            = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.RESTRICT,
        related_name='clicks'
    )
    affiliate           = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.RESTRICT,
        related_name='clicks'
    )
    clicked_at = models.DateTimeField()
    ip_address          = models.GenericIPAddressField(null=True, blank=True)
    user_agent          = models.TextField(null=True, blank=True)
    referrer_url        = models.TextField(null=True, blank=True)
    session_fingerprint = models.CharField(max_length=128, null=True, blank=True)
    is_duplicate        = models.BooleanField(default=False)
    conversion          = models.ForeignKey(
        'Conversion', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='clicks'
    )

    class Meta:
        db_table = 'link_clicks'
        ordering = ['-clicked_at']


class Conversion(models.Model):
    ATTRIBUTION_SOURCES = [
        ('coupon_code',    'Coupon Code'),
        ('tracking_link',  'Tracking Link'),
        ('unattributed',   'Unattributed'),
    ]

    id                      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign                = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.RESTRICT,
        related_name='conversions'
    )
    affiliate               = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.RESTRICT,
        related_name='conversions'
    )
    attribution_source      = models.CharField(max_length=16, choices=ATTRIBUTION_SOURCES)
    affiliate_link          = models.ForeignKey(
        AffiliateLink, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='conversions'
    )
    affiliate_code          = models.ForeignKey(
        AffiliateCode, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='conversions'
    )
    merchant_subscription_id = models.CharField(max_length=128)
    merchant_id = models.CharField(max_length=128)
    merchant_name = models.CharField(max_length=255, null=True, blank=True)
    registration_at = models.DateTimeField()
    is_self_referral = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    converted_at = models.DateTimeField(null=True, blank=True)  # when subscription fired
    lead = models.ForeignKey(
        'MerchantLead', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='conversions'
    )

    class Meta:
        db_table = 'conversions'
        ordering = ['-created_at']


class Commission(models.Model):
    STATUS_CHOICES = [
        ('earned',   'Earned'),
        ('reversed', 'Reversed'),
        ('pending',  'Pending'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversion = models.ForeignKey(
        Conversion,
        on_delete=models.RESTRICT,
        related_name='commissions'
    )
    affiliate = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.RESTRICT,
        related_name='commissions'
    )
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.RESTRICT,
        related_name='commissions'
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='earned')
    amount = models.IntegerField()
    payment_amount = models.IntegerField()
    commission_type_snapshot = models.CharField(max_length=24)
    commission_value_snapshot = models.IntegerField()
    commission_cap_snapshot = models.IntegerField(null=True, blank=True)
    external_payment_id = models.CharField(max_length=128, null=True, blank=True)
    reversed_commission = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reversals'
    )
    earned_at = models.DateTimeField()
    reversed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'commissions'
        ordering = ['-earned_at']


class CentralWallet(models.Model):
    id = models.AutoField(primary_key=True)
    balance = models.IntegerField(default=0)
    total_commissions_allocated = models.IntegerField(default=0)
    total_payouts_made = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'central_wallet'

    def save(self, *args, **kwargs):
        self.id = 1  # Always single row
        super().save(*args, **kwargs)


class MerchantLead(models.Model):
    STATUS_CHOICES = [
        ('trial',      'Trial'),
        ('signed_up',  'Signed Up'),
        ('subscribed', 'Subscribed'),
        ('expired',    'Expired'),
        ('cancelled',  'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affiliate_code = models.ForeignKey(
        AffiliateCode,
        on_delete=models.PROTECT,
        related_name='leads'
    )
    affiliate = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.PROTECT,
        related_name='leads'
    )
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.PROTECT,
        related_name='leads'
    )
    merchant_id = models.CharField(max_length=128, unique=True)
    merchant_name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='trial')
    subscription_tier = models.CharField(max_length=32, null=True, blank=True)
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    amount_paid_kobo = models.IntegerField(null=True, blank=True)
    total_amount_paid_kobo = models.IntegerField(default=0)
    first_subscribed_at = models.DateTimeField(null=True, blank=True)
    first_subscription_tier = models.CharField(max_length=32, null=True, blank=True)
    signed_up_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'merchant_leads'
        ordering = ['-signed_up_at']

class CentralWalletEvent(models.Model):
    EVENT_TYPES = [
        ('credit',   'Commission Credit'),
        ('payout',   'Payout Disbursement'),
        ('reversal', 'Commission Reversal'),
        ('fee',      'Transfer Fee'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type     = models.CharField(max_length=16, choices=EVENT_TYPES)
    amount         = models.IntegerField()          # positive = credit, negative = debit
    balance_after  = models.IntegerField()          # central wallet balance after this event
    description    = models.CharField(max_length=255)
    affiliate      = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='wallet_events',
    )
    commission     = models.ForeignKey(
        'tracking.Commission',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='wallet_events',
    )
    payout_request = models.ForeignKey(
        'payouts.PayoutRequest',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='wallet_events',
    )
    status         = models.CharField(max_length=16, default='done')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table  = 'central_wallet_events'
        ordering  = ['-created_at']