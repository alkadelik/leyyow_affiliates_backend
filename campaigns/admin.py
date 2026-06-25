from django.contrib import admin
from campaigns.models import MerchantOffer


@admin.register(MerchantOffer)
class MerchantOfferAdmin(admin.ModelAdmin):
    list_display  = ('campaign', 'applicable_to', 'type', 'discount_recurrence', 'offer_valid_from', 'offer_valid_until')
    list_filter   = ('applicable_to', 'type', 'discount_recurrence', 'has_lifetime_condition')
    raw_id_fields = ('campaign',)
