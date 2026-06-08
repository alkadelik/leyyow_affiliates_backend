from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

# ── Accounts ──────────────────────────────────────────────────────────────────
from accounts.models import Admin, Affiliate, AffiliateTokenBlacklist

@admin.register(Admin)
class AdminAdmin(admin.ModelAdmin):
    list_display    = ('email', 'full_name', 'role', 'is_active', 'created_at')
    list_filter     = ('role', 'is_active')
    search_fields   = ('email', 'full_name')
    readonly_fields = ('created_at', 'updated_at', 'last_login_at')
    ordering        = ('-created_at',)
    fieldsets = (
        ('Account', {'fields': ('email', 'full_name', 'role', 'is_active')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'last_login_at'), 'classes': ('collapse',)}),
    )

@admin.register(Affiliate)
class AffiliateAdmin(admin.ModelAdmin):
    list_display    = ('email', 'full_name', 'status', 'created_at')
    list_filter     = ('status',)
    search_fields   = ('email', 'full_name')
    readonly_fields = ('created_at', 'updated_at', 'invite_token', 'invite_expires_at')
    ordering        = ('-created_at',)
    fieldsets = (
        ('Account',     {'fields': ('email', 'full_name', 'status')}),
        ('Invite',      {'fields': ('invite_token', 'invite_expires_at'), 'classes': ('collapse',)}),
        ('Timestamps',  {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

@admin.register(AffiliateTokenBlacklist)
class AffiliateTokenBlacklistAdmin(admin.ModelAdmin):
    list_display  = ('token_jti', 'blacklisted_at')
    search_fields = ('token_jti',)
    ordering      = ('-blacklisted_at',)


# ── Campaigns ─────────────────────────────────────────────────────────────────
from campaigns.models import Campaign, CampaignAffiliate

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display    = ('name', 'status', 'commission_type', 'commission_value_display', 'starts_at', 'ends_at', 'created_at')
    list_filter     = ('status', 'commission_type')
    search_fields   = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'created_by', 'cancelled_at', 'cancelled_by', 'ended_at')
    ordering        = ('-created_at',)

    def commission_value_display(self, obj):
        if obj.commission_type == 'flat_fee':
            return f'₦{obj.commission_value / 100:,.0f}'
        return f'{obj.commission_value / 100}%'
    commission_value_display.short_description = 'Commission'

# @admin.register(CampaignAffiliate)
# class CampaignAffiliateAdmin(admin.ModelAdmin):
#     list_display  = ('campaign', 'affiliate', 'assigned_at', 'removed_at')
#     list_filter   = ('campaign__status',)
#     search_fields = ('campaign__name', 'affiliate__email', 'affiliate__full_name')
#     readonly_fields = ('assigned_at', 'assigned_by', 'removed_at', 'removed_by')
#     ordering      = ('-assigned_at',)

@admin.register(CampaignAffiliate)
class CampaignAffiliateAdmin(admin.ModelAdmin):
    list_display    = ('campaign_name', 'affiliate', 'assigned_at', 'removed_at')
    list_filter     = ('campaign__status',)
    search_fields   = ('campaign__name', 'affiliate__email', 'affiliate__full_name')
    readonly_fields = ('assigned_at', 'assigned_by', 'removed_at', 'removed_by')
    ordering        = ('-assigned_at',)

    def campaign_name(self, obj):
        return obj.campaign.name
    campaign_name.short_description = 'Campaign'

# ── Tracking ──────────────────────────────────────────────────────────────────
from tracking.models import AffiliateLink, AffiliateCode, LinkClick, Conversion, Commission, CentralWallet
from accounts.models import Admin, Affiliate, AffiliateTokenBlacklist, AffiliateWallet

@admin.register(AffiliateLink)
class AffiliateLinkAdmin(admin.ModelAdmin):
    list_display  = ('affiliate', 'campaign', 'slug', 'click_count', 'created_at')
    search_fields = ('slug', 'affiliate__email', 'campaign__name')
    readonly_fields = ('created_at',)
    ordering      = ('-created_at',)

@admin.register(AffiliateCode)
class AffiliateCodeAdmin(admin.ModelAdmin):
    list_display  = ('affiliate', 'campaign', 'code', 'is_custom', 'use_count', 'created_at')
    search_fields = ('code', 'affiliate__email', 'campaign__name')
    readonly_fields = ('created_at', 'updated_at')
    ordering      = ('-created_at',)

@admin.register(LinkClick)
class LinkClickAdmin(admin.ModelAdmin):
    list_display  = ('affiliate_link', 'clicked_at', 'ip_address')
    search_fields = ('affiliate_link__slug',)
    readonly_fields = ('clicked_at',)
    ordering      = ('-clicked_at',)

@admin.register(Conversion)
class ConversionAdmin(admin.ModelAdmin):
    list_display    = ('affiliate', 'campaign', 'merchant_name', 'attribution_source', 'created_at')
    list_filter     = ('attribution_source',)
    search_fields   = ('affiliate__email', 'campaign__name', 'merchant_name', 'merchant_id')
    readonly_fields = ('created_at',)
    ordering        = ('-created_at',)

@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display    = ('affiliate', 'campaign', 'amount_display', 'status', 'earned_at')
    list_filter     = ('status',)
    search_fields   = ('affiliate__email', 'campaign__name')
    readonly_fields = ('earned_at',)
    ordering        = ('-earned_at',)

    def amount_display(self, obj):
        return f'₦{obj.amount / 100:,.0f}'
    amount_display.short_description = 'Amount'

@admin.register(AffiliateWallet)
class AffiliateWalletAdmin(admin.ModelAdmin):
    list_display  = ('affiliate', 'balance_display', 'updated_at')
    search_fields = ('affiliate__email', 'affiliate__full_name')
    readonly_fields = ('created_at', 'updated_at')

    def balance_display(self, obj):
        return f'₦{obj.balance / 100:,.0f}'
    balance_display.short_description = 'Balance'

@admin.register(CentralWallet)
class CentralWalletAdmin(admin.ModelAdmin):
    list_display  = ('id', 'balance_display', 'total_commissions_allocated', 'total_payouts_made', 'updated_at')
    readonly_fields = ('updated_at',)

    def balance_display(self, obj):
        return f'₦{obj.balance / 100:,.0f}'
    balance_display.short_description = 'Balance'


# ── Payouts ───────────────────────────────────────────────────────────────────
from payouts.models import BankAccount, PayoutRequest

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display    = ('affiliate', 'bank_name', 'account_name', 'account_number', 'is_default', 'deleted_at')
    list_filter     = ('is_default',)
    search_fields   = ('affiliate__email', 'bank_name', 'account_number')
    readonly_fields = ('created_at', 'updated_at')
    ordering        = ('-created_at',)

@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    list_display    = ('affiliate', 'amount_display', 'status', 'requested_at', 'reviewed_at', 'paid_at')
    list_filter     = ('status',)
    search_fields   = ('affiliate__email',)
    readonly_fields = ('requested_at', 'reviewed_at', 'paid_at', 'reviewed_by')
    ordering        = ('-requested_at',)

    def amount_display(self, obj):
        return f'₦{obj.requested_amount / 100:,.0f}'
    amount_display.short_description = 'Amount'


# ── Audit ─────────────────────────────────────────────────────────────────────
from audit.models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display    = ('action', 'actor_type', 'actor_id', 'entity_type', 'entity_id', 'created_at')
    list_filter     = ('actor_type', 'entity_type')
    search_fields   = ('action', 'actor_id', 'entity_id')
    readonly_fields = ('created_at',)
    ordering        = ('-created_at',)