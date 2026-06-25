import uuid
from django.db import models


class Campaign(models.Model):
    STATUS_CHOICES = [
        ('draft',     'Draft'),
        ('scheduled', 'Scheduled'),
        ('active',    'Active'),
        ('ended',     'Ended'),
        ('cancelled', 'Cancelled'),
    ]

    CAMPAIGN_TYPE_CHOICES = [
        ('fixed',  'Fixed'),
        ('tiered', 'Tiered'),
    ]

    COMMISSION_TYPES = [
        ('flat_fee',          'Flat Fee'),
        ('percentage',        'Percentage'),
        ('percentage_capped', 'Percentage Capped'),
    ]

    COMMISSION_TRIGGER_CHOICES = [
        ('first_subscription_only',     'First Subscription Only'),
        ('all_subscriptions',           'All Subscriptions'),
        ('subscriptions_within_period', 'Subscriptions Within Period'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    campaign_type = models.CharField(max_length=16, choices=CAMPAIGN_TYPE_CHOICES, default='fixed')
    commission_type = models.CharField(max_length=24, choices=COMMISSION_TYPES, null=True, blank=True)
    commission_value = models.IntegerField(null=True, blank=True)
    commission_cap = models.IntegerField(null=True, blank=True)
    commission_trigger = models.CharField(max_length=32, choices=COMMISSION_TRIGGER_CHOICES, null=True, blank=True)
    commission_period_days = models.IntegerField(null=True, blank=True)
    commission_per_tier = models.JSONField(null=True, blank=True)
    subscriber_tiers = models.JSONField(null=True, blank=True)
    tiered_period_days = models.IntegerField(null=True, blank=True, default=90)
    tier = models.CharField(max_length=32, null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    conversion_limit = models.IntegerField(null=True, blank=True)
    terms_and_conditions = models.TextField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        'accounts.Admin', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='cancelled_campaigns',
        db_column='cancelled_by'
    )
    created_by = models.ForeignKey(
        'accounts.Admin',
        on_delete=models.PROTECT,
        related_name='created_campaigns',
        db_column='created_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'campaigns'
        ordering = ['-created_at']


class CampaignAffiliate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.RESTRICT,
        related_name='campaign_affiliates'
    )
    affiliate = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.RESTRICT,
        related_name='campaign_affiliates'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        'accounts.Admin',
        on_delete=models.PROTECT,
        related_name='assigned_campaign_affiliates',
        db_column='assigned_by'
    )
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey(
        'accounts.Admin', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='removed_campaign_affiliates',
        db_column='removed_by'
    )

    class Meta:
        db_table = 'campaign_affiliates'
        unique_together = [('campaign', 'affiliate')]


class MerchantOffer(models.Model):
    APPLICABLE_TO_CHOICES = [
        ('trial',        'Trial'),
        ('subscription', 'Subscription'),
    ]
    TYPE_CHOICES = [
        ('extension', 'Extension'),
        ('discount',  'Discount'),
    ]
    DISCOUNT_SUBTYPE_CHOICES = [
        ('amount',     'Amount'),
        ('percentage', 'Percentage'),
    ]
    RECURRENCE_CHOICES = [
        ('once',    'Once'),
        ('n_times', 'N Times'),
        ('forever', 'Forever'),
    ]

    id                              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign                        = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='offers')
    applicable_to                   = models.CharField(max_length=16, choices=APPLICABLE_TO_CHOICES)
    type                            = models.CharField(max_length=16, choices=TYPE_CHOICES)
    extension_days                  = models.IntegerField(null=True, blank=True)
    discount_subtype                = models.CharField(max_length=16, choices=DISCOUNT_SUBTYPE_CHOICES, null=True, blank=True)
    discount_value                  = models.IntegerField(null=True, blank=True)
    discount_recurrence             = models.CharField(max_length=16, choices=RECURRENCE_CHOICES, null=True, blank=True)
    discount_recurrence_count       = models.IntegerField(null=True, blank=True)
    has_lifetime_condition          = models.BooleanField(default=False)
    condition_type                  = models.CharField(max_length=32, null=True, blank=True)
    condition_threshold             = models.IntegerField(null=True, blank=True)
    merchant_redemption_window_days = models.IntegerField()
    offer_valid_from                = models.DateTimeField()
    offer_valid_until               = models.DateTimeField(null=True, blank=True)
    created_at                      = models.DateTimeField(auto_now_add=True)
    updated_at                      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'merchant_offers'
        ordering = ['-created_at']