from campaigns.models import Campaign, CampaignAffiliate
from accounts.models import Affiliate
from rest_framework import serializers


class MerchantOfferSerializer(serializers.Serializer):
    applicable_to                   = serializers.ChoiceField(choices=['trial', 'subscription'])
    type                            = serializers.ChoiceField(choices=['extension', 'discount'])
    extension_days                  = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    discount_subtype                = serializers.ChoiceField(choices=['amount', 'percentage'], required=False, allow_null=True)
    discount_value                  = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    discount_recurrence             = serializers.ChoiceField(choices=['once', 'n_times', 'forever'], required=False, allow_null=True)
    discount_recurrence_count       = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    has_lifetime_condition          = serializers.BooleanField(default=False)
    condition_type                  = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    condition_threshold             = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    merchant_redemption_window_days = serializers.IntegerField(min_value=1)
    offer_valid_from                = serializers.DateTimeField()
    offer_valid_until               = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, data):
        if data.get('type') == 'extension':
            if not data.get('extension_days'):
                raise serializers.ValidationError({'extension_days': 'Required for extension offers.'})
        elif data.get('type') == 'discount':
            if not data.get('discount_subtype'):
                raise serializers.ValidationError({'discount_subtype': 'Required for discount offers.'})
            if not data.get('discount_value'):
                raise serializers.ValidationError({'discount_value': 'Required for discount offers.'})
            if not data.get('discount_recurrence'):
                raise serializers.ValidationError({'discount_recurrence': 'Required for discount offers.'})
            if data.get('discount_recurrence') == 'n_times' and not data.get('discount_recurrence_count'):
                raise serializers.ValidationError({'discount_recurrence_count': 'Required when recurrence is n_times.'})
        if data.get('has_lifetime_condition'):
            if not data.get('condition_type'):
                raise serializers.ValidationError({'condition_type': 'Required when has_lifetime_condition is true.'})
            if not data.get('condition_threshold'):
                raise serializers.ValidationError({'condition_threshold': 'Required when has_lifetime_condition is true.'})
        return data


COMMISSION_TRIGGER_CHOICES = [
    ('first_subscription_only',     'First Subscription Only'),
    ('all_subscriptions',           'All Subscriptions'),
    ('subscriptions_within_period', 'Subscriptions Within Period'),
]


class CampaignListSerializer(serializers.ModelSerializer):
    affiliate_count  = serializers.SerializerMethodField()
    created_by_name  = serializers.SerializerMethodField()
    conversion_count = serializers.SerializerMethodField()

    class Meta:
        model  = Campaign
        fields = [
            'id', 'name', 'status', 'campaign_type',
            'commission_type', 'commission_value', 'commission_cap', 'tier',
            'subscriber_tiers',
            'starts_at', 'ends_at', 'conversion_limit',
            'commission_trigger', 'commission_period_days', 'commission_per_tier',
            'affiliate_count', 'created_by_name', 'created_at',
            'conversion_count',
        ]

    def get_affiliate_count(self, obj):
        return obj.campaign_affiliates.filter(removed_at__isnull=True).count()

    def get_created_by_name(self, obj):
        return obj.created_by.full_name

    def get_conversion_count(self, obj):
        from tracking.models import MerchantLead
        return MerchantLead.objects.filter(campaign=obj, status__in=['subscribed', 'renewed']).count()


class CampaignDetailSerializer(serializers.ModelSerializer):
    affiliates      = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    offer           = serializers.SerializerMethodField()

    class Meta:
        model  = Campaign
        fields = [
            'id', 'name', 'description', 'status', 'campaign_type',
            'commission_type', 'commission_value', 'commission_cap',
            'tier', 'subscriber_tiers',
            'starts_at', 'ends_at', 'conversion_limit',
            'commission_trigger', 'commission_period_days', 'commission_per_tier',
            'terms_and_conditions', 'ended_at', 'cancelled_at',
            'created_by_name', 'created_at', 'updated_at', 'affiliates', 'offer',
        ]

    def get_affiliates(self, obj):
        active_assignments = obj.campaign_affiliates.filter(
            removed_at__isnull=True
        ).select_related('affiliate').prefetch_related('code')
        return [
            {
                'id':             str(ca.affiliate.id),
                'full_name':      ca.affiliate.full_name,
                'email':          ca.affiliate.email,
                'status':         ca.affiliate.status,
                'affiliate_code': ca.code.code if hasattr(ca, 'code') else None,
            }
            for ca in active_assignments
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.full_name

    def get_offer(self, obj):
        offer = obj.offers.first()
        if not offer:
            return None
        return {
            'id':                              str(offer.id),
            'applicable_to':                   offer.applicable_to,
            'type':                            offer.type,
            'extension_days':                  offer.extension_days,
            'discount_subtype':                offer.discount_subtype,
            'discount_value':                  offer.discount_value,
            'discount_recurrence':             offer.discount_recurrence,
            'discount_recurrence_count':       offer.discount_recurrence_count,
            'has_lifetime_condition':          offer.has_lifetime_condition,
            'condition_type':                  offer.condition_type,
            'condition_threshold':             offer.condition_threshold,
            'merchant_redemption_window_days': offer.merchant_redemption_window_days,
            'offer_valid_from':                offer.offer_valid_from,
            'offer_valid_until':               offer.offer_valid_until,
        }


class CreateCampaignSerializer(serializers.Serializer):
    name                 = serializers.CharField(max_length=255)
    description          = serializers.CharField(required=False, allow_blank=True)
    campaign_type        = serializers.ChoiceField(choices=['fixed', 'tiered'], default='fixed')
    commission_type      = serializers.ChoiceField(
        choices=['flat_fee', 'percentage', 'percentage_capped'],
        required=False, allow_null=True,
    )
    commission_value     = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    commission_cap       = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    subscriber_tiers     = serializers.JSONField(required=False, allow_null=True)
    tier                 = serializers.CharField(required=False, allow_blank=True)
    starts_at            = serializers.DateTimeField(required=False, allow_null=True)
    ends_at              = serializers.DateTimeField(required=False, allow_null=True)
    conversion_limit     = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    terms_and_conditions = serializers.CharField(required=False, allow_blank=True)
    commission_trigger   = serializers.ChoiceField(
        choices=COMMISSION_TRIGGER_CHOICES,
        required=False, allow_blank=True, allow_null=True,
    )
    commission_period_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    commission_per_tier    = serializers.JSONField(required=False, allow_null=True)
    offer                  = MerchantOfferSerializer(required=False, allow_null=True)

    def validate(self, data):
        is_draft      = self.context.get('is_draft', False)
        campaign_type = data.get('campaign_type', 'fixed')
        starts_at     = data.get('starts_at')
        ends_at       = data.get('ends_at')

        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {'ends_at': 'End date must be after start date.'}
            )

        if campaign_type == 'tiered':
            subscriber_tiers = data.get('subscriber_tiers')
            if not is_draft:
                if not subscriber_tiers or not isinstance(subscriber_tiers, list) or len(subscriber_tiers) == 0:
                    raise serializers.ValidationError(
                        {'subscriber_tiers': 'At least one tier is required for tiered campaigns.'}
                    )
                if starts_at is None:
                    raise serializers.ValidationError({'starts_at': 'Start date is required.'})
            if subscriber_tiers:
                self._validate_subscriber_tiers(subscriber_tiers)
            # tiered campaigns always fire on every subscription — no trigger needed
            data['commission_trigger'] = None
            data['commission_period_days'] = None
            data.setdefault('commission_type', None)
            data.setdefault('commission_value', None)
            return data

        # ── Fixed campaign validation ──────────────────────────────────────────
        commission_type    = data.get('commission_type')
        commission_cap     = data.get('commission_cap')
        commission_trigger = data.get('commission_trigger')
        period_days        = data.get('commission_period_days')

        if not is_draft:
            if not data.get('commission_value'):
                raise serializers.ValidationError({'commission_value': 'Commission value is required.'})
            if not commission_trigger:
                raise serializers.ValidationError({'commission_trigger': 'Commission trigger is required.'})
            if starts_at is None:
                raise serializers.ValidationError({'starts_at': 'Start date is required.'})

        if commission_type == 'percentage_capped' and not commission_cap:
            raise serializers.ValidationError(
                {'commission_cap': 'A commission cap is required for percentage_capped campaigns.'}
            )
        if commission_type == 'percentage' and data.get('commission_value', 0) and data['commission_value'] > 10000:
            raise serializers.ValidationError(
                {'commission_value': 'Percentage value cannot exceed 10000 basis points (100%).'}
            )
        if not is_draft and commission_trigger == 'subscriptions_within_period' and not period_days:
            raise serializers.ValidationError(
                {'commission_period_days': 'Required when commission_trigger is subscriptions_within_period.'}
            )
        if commission_trigger != 'subscriptions_within_period':
            data['commission_period_days'] = None

        return data

    def _validate_subscriber_tiers(self, tiers):
        for i, tier in enumerate(tiers):
            label = f'Tier {i + 1}'
            if 'min_subs' not in tier:
                raise serializers.ValidationError(
                    {'subscriber_tiers': f'{label}: min_subs is required.'}
                )
            if tier.get('min_subs', 0) < 0:
                raise serializers.ValidationError(
                    {'subscriber_tiers': f'{label}: min_subs must be >= 0.'}
                )
            if 'commission_type' not in tier or tier['commission_type'] not in ('flat_fee', 'percentage'):
                raise serializers.ValidationError(
                    {'subscriber_tiers': f'{label}: commission_type must be flat_fee or percentage.'}
                )
            if 'commission_value' not in tier or tier.get('commission_value', -1) < 0:
                raise serializers.ValidationError(
                    {'subscriber_tiers': f'{label}: commission_value must be >= 0.'}
                )
            if tier['commission_type'] == 'percentage' and tier.get('commission_value', 0) > 10000:
                raise serializers.ValidationError(
                    {'subscriber_tiers': f'{label}: percentage cannot exceed 10000 basis points (100%).'}
                )
            max_s = tier.get('max_subs')
            if max_s is not None and max_s < tier['min_subs']:
                raise serializers.ValidationError(
                    {'subscriber_tiers': f'{label}: max_subs must be >= min_subs.'}
                )

        # All tiers must use the same commission type
        types = {tier['commission_type'] for tier in tiers}
        if len(types) > 1:
            raise serializers.ValidationError(
                {'subscriber_tiers': 'All tiers must use the same commission type (flat fee or percentage).'}
            )


class UpdateCampaignSerializer(CreateCampaignSerializer):
    name             = serializers.CharField(max_length=255, required=False)
    campaign_type    = serializers.ChoiceField(choices=['fixed', 'tiered'], required=False)
    commission_type  = serializers.ChoiceField(
        choices=['flat_fee', 'percentage', 'percentage_capped'],
        required=False, allow_blank=True, allow_null=True,
    )
    commission_value   = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    commission_trigger = serializers.ChoiceField(
        choices=COMMISSION_TRIGGER_CHOICES,
        required=False, allow_blank=True, allow_null=True,
    )


class TransitionCampaignSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['schedule', 'start', 'end', 'cancel'])


class AssignAffiliateSerializer(serializers.Serializer):
    affiliate_id = serializers.UUIDField()

    def validate_affiliate_id(self, value):
        try:
            Affiliate.objects.get(id=value, status__in=['inactive', 'active'])
        except Affiliate.DoesNotExist:
            raise serializers.ValidationError('Affiliate not found.')
        return value


class RemoveAffiliateSerializer(serializers.Serializer):
    affiliate_id = serializers.UUIDField()
