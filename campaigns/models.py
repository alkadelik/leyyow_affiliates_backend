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
    commission_type = models.CharField(max_length=24, choices=COMMISSION_TYPES)
    commission_value = models.IntegerField(null=True, blank=True)
    commission_cap = models.IntegerField(null=True, blank=True)
    commission_trigger = models.CharField(max_length=32, choices=COMMISSION_TRIGGER_CHOICES, null=True, blank=True)
    commission_period_days = models.IntegerField(null=True, blank=True)
    commission_per_tier = models.JSONField(null=True, blank=True)
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