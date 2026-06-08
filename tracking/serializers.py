from rest_framework import serializers
from tracking.models import AffiliateLink, AffiliateCode, LinkClick, Conversion, Commission


class AffiliateLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AffiliateLink
        fields = ['id', 'slug', 'full_url', 'click_count', 'created_at']


class AffiliateCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AffiliateCode
        fields = ['id', 'code', 'is_custom', 'use_count', 'created_at', 'updated_at']


class UpdateAffiliateCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)

    def validate_code(self, value):
        value = value.upper().strip()
        if AffiliateCode.objects.filter(code=value).exclude(
            id=self.context.get('code_id')
        ).exists():
            raise serializers.ValidationError(
                'This code is already taken. Please choose another.'
            )
        return value


class TrackClickSerializer(serializers.Serializer):
    slug = serializers.CharField(max_length=32)


class RecordConversionSerializer(serializers.Serializer):
    merchant_subscription_id = serializers.CharField(max_length=128)
    merchant_id              = serializers.CharField(max_length=128)
    merchant_name            = serializers.CharField(max_length=255, required=False)
    payment_amount           = serializers.IntegerField(min_value=1)
    external_payment_id      = serializers.CharField(max_length=128, required=False)
    coupon_code              = serializers.CharField(max_length=32, required=False, allow_blank=True)
    session_fingerprint      = serializers.CharField(max_length=128, required=False, allow_blank=True)
    affiliate_id             = serializers.UUIDField(required=False, allow_null=True)


class ConversionSerializer(serializers.ModelSerializer):
    affiliate_name = serializers.SerializerMethodField()
    campaign_name  = serializers.SerializerMethodField()

    class Meta:
        model  = Conversion
        fields = [
            'id', 'campaign', 'campaign_name', 'affiliate', 'affiliate_name',
            'attribution_source', 'merchant_subscription_id', 'merchant_id',
            'merchant_name', 'registration_at', 'is_self_referral', 'created_at',
        ]

    def get_affiliate_name(self, obj):
        return obj.affiliate.full_name if obj.affiliate else None

    def get_campaign_name(self, obj):
        return obj.campaign.name


class CommissionSerializer(serializers.ModelSerializer):
    affiliate_name = serializers.SerializerMethodField()
    campaign_name  = serializers.SerializerMethodField()

    class Meta:
        model  = Commission
        fields = [
            'id', 'conversion', 'affiliate', 'affiliate_name',
            'campaign', 'campaign_name', 'status', 'amount',
            'payment_amount', 'commission_type_snapshot',
            'commission_value_snapshot', 'earned_at', 'reversed_at',
        ]

    def get_affiliate_name(self, obj):
        return obj.affiliate.full_name

    def get_campaign_name(self, obj):
        return obj.campaign.name
    
# ── Affiliate portal serializers ─────────────────────────────────────────────

class AffiliateCampaignListSerializer(serializers.Serializer):
    """Campaign as seen by the affiliate — includes their link and code."""
    id              = serializers.UUIDField()
    name            = serializers.CharField()
    description     = serializers.CharField()
    status          = serializers.CharField()
    commission_type  = serializers.CharField()
    commission_value = serializers.IntegerField()
    commission_cap   = serializers.IntegerField(allow_null=True)
    tier             = serializers.CharField(allow_null=True)
    starts_at        = serializers.DateTimeField(allow_null=True)
    ends_at          = serializers.DateTimeField(allow_null=True)
    terms_and_conditions = serializers.CharField(allow_null=True)
    link             = serializers.DictField(allow_null=True)
    code             = serializers.DictField(allow_null=True)
    total_clicks     = serializers.IntegerField()
    total_conversions = serializers.IntegerField()
    total_earned     = serializers.IntegerField()


class AffiliateCommissionSerializer(serializers.ModelSerializer):
    campaign_name = serializers.SerializerMethodField()
    merchant_name = serializers.SerializerMethodField()

    class Meta:
        model  = Commission
        fields = [
            'id', 'status', 'amount', 'payment_amount',
            'commission_type_snapshot', 'campaign_name',
            'merchant_name', 'earned_at', 'reversed_at',
        ]

    def get_campaign_name(self, obj):
        return obj.campaign.name

    def get_merchant_name(self, obj):
        return obj.conversion.merchant_name