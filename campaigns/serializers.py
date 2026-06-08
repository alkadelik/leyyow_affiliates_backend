from campaigns.models import Campaign, CampaignAffiliate
from accounts.models import Affiliate
from rest_framework import serializers


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
            'id', 'name', 'status', 'commission_type',
            'commission_value', 'commission_cap', 'tier',
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
        return MerchantLead.objects.filter(campaign=obj, status='subscribed').count()


class CampaignDetailSerializer(serializers.ModelSerializer):
    affiliates      = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = Campaign
        fields = [
            'id', 'name', 'description', 'status',
            'commission_type', 'commission_value', 'commission_cap',
            'tier', 'starts_at', 'ends_at', 'conversion_limit',
            'commission_trigger', 'commission_period_days', 'commission_per_tier',
            'terms_and_conditions', 'ended_at', 'cancelled_at',
            'created_by_name', 'created_at', 'updated_at', 'affiliates',
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


class CreateCampaignSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    commission_type = serializers.ChoiceField(choices=['flat_fee', 'percentage', 'percentage_capped'])
    commission_value = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    commission_cap = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    tier = serializers.CharField(required=False, allow_blank=True)
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    conversion_limit = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    terms_and_conditions = serializers.CharField(required=False, allow_blank=True)
    commission_trigger = serializers.ChoiceField(choices=COMMISSION_TRIGGER_CHOICES, required=False, allow_blank=True, allow_null=True,)
    commission_period_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    commission_per_tier = serializers.JSONField(required=False, allow_null=True)

    def validate(self, data):
        is_draft = self.context.get('is_draft', False)
        commission_type = data.get('commission_type')
        commission_cap = data.get('commission_cap')
        starts_at = data.get('starts_at')
        ends_at = data.get('ends_at')
        commission_trigger = data.get('commission_trigger')
        period_days = data.get('commission_period_days')

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
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {'ends_at': 'End date must be after start date.'}
            )
        if not is_draft and commission_trigger == 'subscriptions_within_period' and not period_days:
            raise serializers.ValidationError(
                {'commission_period_days': 'Required when commission_trigger is subscriptions_within_period.'}
            )
        if commission_trigger != 'subscriptions_within_period':
            data['commission_period_days'] = None

        return data
    

class UpdateCampaignSerializer(CreateCampaignSerializer):
    name = serializers.CharField(max_length=255, required=False)
    commission_type = serializers.ChoiceField(choices=['flat_fee', 'percentage', 'percentage_capped'], required=False)
    commission_value = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    commission_trigger = serializers.ChoiceField(choices=COMMISSION_TRIGGER_CHOICES, required=False, allow_blank=True, allow_null=True)


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