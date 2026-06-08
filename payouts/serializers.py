from rest_framework import serializers
from payouts.models import BankAccount, PayoutRequest


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BankAccount
        fields = [
            'id', 'bank_name', 'bank_code', 'account_number',
            'account_name', 'is_default', 'created_at',
        ]


class AddBankAccountSerializer(serializers.Serializer):
    bank_name      = serializers.CharField(max_length=128)
    bank_code      = serializers.CharField(max_length=16)
    account_number = serializers.CharField(max_length=20)
    account_name   = serializers.CharField(max_length=255)
    is_default     = serializers.BooleanField(default=False)

    def validate_account_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError('Account number must contain digits only.')
        if len(value) != 10:
            raise serializers.ValidationError('Account number must be 10 digits.')
        return value


class PayoutRequestSerializer(serializers.ModelSerializer):
    bank_account_detail = serializers.SerializerMethodField()

    class Meta:
        model  = PayoutRequest
        fields = [
            'id', 'status', 'requested_amount', 'transfer_fee',
            'net_amount', 'balance_at_request', 'requested_at',
            'reviewed_at', 'paid_at', 'failure_reason',
            'bank_account_detail',
        ]

    def get_bank_account_detail(self, obj):
        return {
            'bank_name':      obj.bank_account.bank_name,
            'account_number': obj.bank_account.account_number,
            'account_name':   obj.bank_account.account_name,
        }


class CreatePayoutRequestSerializer(serializers.Serializer):
    bank_account_id  = serializers.UUIDField()
    requested_amount = serializers.IntegerField(min_value=1)

    def validate_bank_account_id(self, value):
        from payouts.models import BankAccount
        if not BankAccount.objects.filter(id=value, deleted_at__isnull=True).exists():
            raise serializers.ValidationError('Bank account not found.')
        return value


class AdminPayoutRequestSerializer(serializers.ModelSerializer):
    affiliate_name      = serializers.SerializerMethodField()
    affiliate_email     = serializers.SerializerMethodField()
    bank_account_detail = serializers.SerializerMethodField()
    reviewed_by_name    = serializers.SerializerMethodField()

    class Meta:
        model  = PayoutRequest
        fields = [
            'id', 'status', 'requested_amount', 'transfer_fee',
            'net_amount', 'balance_at_request', 'requested_at',
            'reviewed_at', 'paid_at', 'failure_reason', 'admin_notes',
            'affiliate_name', 'affiliate_email',
            'bank_account_detail', 'reviewed_by_name',
        ]

    def get_affiliate_name(self, obj):
        return obj.affiliate.full_name

    def get_affiliate_email(self, obj):
        return obj.affiliate.email

    def get_bank_account_detail(self, obj):
        return {
            'bank_name':      obj.bank_account.bank_name,
            'account_number': obj.bank_account.account_number,
            'account_name':   obj.bank_account.account_name,
        }

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by is None and obj.status in ('approved', 'paid'):
            return 'Auto'
        return obj.reviewed_by.full_name if obj.reviewed_by else None


class AdminPayoutActionSerializer(serializers.Serializer):
    action      = serializers.ChoiceField(choices=['approve', 'mark_paid', 'cancel'])
    admin_notes = serializers.CharField(required=False, allow_blank=True)
    failure_reason = serializers.CharField(required=False, allow_blank=True)