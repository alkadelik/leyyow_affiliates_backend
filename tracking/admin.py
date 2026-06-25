from django.contrib import admin
from tracking.models import MerchantOfferRedemption


@admin.register(MerchantOfferRedemption)
class MerchantOfferRedemptionAdmin(admin.ModelAdmin):
    list_display  = ('merchant_lead', 'offer', 'status', 'times_applied', 'expires_at')
    list_filter   = ('status',)
    raw_id_fields = ('merchant_lead', 'offer')
