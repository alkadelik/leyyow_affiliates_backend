from rest_framework import serializers
from accounts.models import Admin, Affiliate
from tracking.models import MerchantLead


class AdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Admin
        fields = ['id', 'email', 'full_name', 'role']


class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token        = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError('Password must contain at least one uppercase letter.')
        if not any(c.islower() for c in value):
            raise serializers.ValidationError('Password must contain at least one lowercase letter.')
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError('Password must contain at least one number.')
        blocklist = ['Password1', 'Leyyow123', 'Admin1234']
        if value in blocklist:
            raise serializers.ValidationError('This password is too common.')
        return value


# ── Affiliate serializers ────────────────────────────────────────────────────

class AffiliateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Affiliate
        fields = ['id', 'email', 'full_name', 'status', 'registered_at', 'created_at']


class CreateAffiliateSerializer(serializers.Serializer):
    email     = serializers.EmailField()
    full_name = serializers.CharField(max_length=255)

    def validate_email(self, value):
        if Affiliate.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('An affiliate with this email already exists.')
        return value.lower()


class ValidateInviteSerializer(serializers.Serializer):
    token = serializers.CharField()


class AffiliateRegisterSerializer(serializers.Serializer):
    token        = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError('Password must contain at least one uppercase letter.')
        if not any(c.islower() for c in value):
            raise serializers.ValidationError('Password must contain at least one lowercase letter.')
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError('Password must contain at least one number.')
        return value


class AffiliateForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class AffiliateResetPasswordSerializer(serializers.Serializer):
    token        = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError('Password must contain at least one uppercase letter.')
        if not any(c.islower() for c in value):
            raise serializers.ValidationError('Password must contain at least one lowercase letter.')
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError('Password must contain at least one number.')
        return value


class AffiliateLoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    

class AffiliateDetailSerializer(serializers.ModelSerializer):
    wallet_balance    = serializers.SerializerMethodField()
    total_earned      = serializers.SerializerMethodField()
    total_paid_out    = serializers.SerializerMethodField()
    default_bank_account = serializers.SerializerMethodField()
    has_pending_payout   = serializers.SerializerMethodField()
    last_referral_at = serializers.SerializerMethodField()

    class Meta:
        model  = Affiliate
        fields = [
            'id', 'email', 'full_name', 'status',
            'registered_at', 'last_login_at',
            'deactivated_at', 'created_at',
            'wallet_balance', 'total_earned', 'total_paid_out',
            'default_bank_account', 'has_pending_payout', 'last_referral_at',
        ]

    def get_wallet_balance(self, obj):
        try: return obj.wallet.balance
        except Exception: return 0

    def get_total_earned(self, obj):
        try: return obj.wallet.total_earned
        except Exception: return 0

    def get_total_paid_out(self, obj):
        try: return obj.wallet.total_withdrawn
        except Exception: return 0

    def get_default_bank_account(self, obj):
        account = obj.bank_accounts.filter(
            is_default=True, deleted_at__isnull=True
        ).first()
        if not account:
            account = obj.bank_accounts.filter(deleted_at__isnull=True).first()
        if not account:
            return None
        return {
            'bank_name':      account.bank_name,
            'account_number': account.account_number,
            'account_name':   account.account_name,
        }

    def get_has_pending_payout(self, obj):
        return obj.payout_requests.filter(status='pending').exists()
    
    def get_last_referral_at(self, obj):
        last = MerchantLead.objects.filter(affiliate=obj).order_by('-signed_up_at').first()
        return last.signed_up_at if last else None


class AffiliateListSerializer(serializers.ModelSerializer):
    wallet_balance      = serializers.SerializerMethodField()
    live_campaign_count = serializers.SerializerMethodField()
    last_referral_at    = serializers.SerializerMethodField()

    class Meta:
        model  = Affiliate
        fields = [
            'id', 'email', 'full_name', 'status',
            'registered_at', 'created_at',
            'wallet_balance', 'live_campaign_count', 'last_referral_at',
        ]

    def get_wallet_balance(self, obj):
        try: return obj.wallet.balance
        except Exception: return 0

    def get_live_campaign_count(self, obj):
        from campaigns.models import CampaignAffiliate
        return CampaignAffiliate.objects.filter(
            affiliate=obj,
            removed_at__isnull=True,
            campaign__status='active'
        ).count()

    def get_last_referral_at(self, obj):
        from tracking.models import MerchantLead
        last = MerchantLead.objects.filter(
            affiliate=obj
        ).order_by('-signed_up_at').first()
        return last.signed_up_at if last else None


class UpdateAffiliateStatusSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['activate', 'deactivate'])

# ── Affiliate portal serializers ─────────────────────────────────────────────

class AffiliateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Affiliate
        fields = ['id', 'email', 'full_name', 'status', 'registered_at']
        read_only_fields = ['id', 'email', 'status', 'registered_at']


class UpdateAffiliateProfileSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)


class ChangeAffiliatePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError('Password must contain at least one uppercase letter.')
        if not any(c.islower() for c in value):
            raise serializers.ValidationError('Password must contain at least one lowercase letter.')
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError('Password must contain at least one number.')
        return value


class AffiliateDashboardSerializer(serializers.Serializer):
    """Serializes the dashboard summary dict built in the view."""
    full_name          = serializers.CharField()
    wallet_balance     = serializers.IntegerField()
    total_earned       = serializers.IntegerField()
    total_withdrawn    = serializers.IntegerField()
    active_campaigns   = serializers.IntegerField()
    total_conversions  = serializers.IntegerField()
    total_clicks       = serializers.IntegerField()
    recent_commissions = serializers.ListField()