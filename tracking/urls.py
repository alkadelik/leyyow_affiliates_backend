from django.urls import path
from tracking.views import (
    TrackClickView,
    GenerateLinkAndCodeView,
    UpdateAffiliateCodeView,
    RecordConversionView,
    ReverseCommissionView,
    AdminConversionListView,
    AdminCommissionListView,
    MerchantLeadListView,
    MerchantLeadDetailView,
)
from tracking.internal_views import MerchantSignupView, MerchantSubscriptionView, MerchantLeadInternalListView

urlpatterns = [
    # Public click tracking — stays at root, no api/ prefix
    path('r/<str:slug>/', TrackClickView.as_view(), name='track-click'),

    # Admin
    path('admin/tracking/generate/', GenerateLinkAndCodeView.as_view(), name='generate-link-code'),
    path('admin/tracking/conversions/', AdminConversionListView.as_view(), name='admin-conversions'),
    path('admin/tracking/commissions/', AdminCommissionListView.as_view(), name='admin-commissions'),

    # Affiliate
    path('affiliate/codes/<uuid:code_id>/', UpdateAffiliateCodeView.as_view(), name='update-code'),

    # Internal
    path('internal/conversions/', RecordConversionView.as_view(), name='record-conversion'),
    path('internal/commissions/<uuid:commission_id>/reverse/', ReverseCommissionView.as_view(), name='reverse-commission'),
    path('internal/merchant-signup/', MerchantSignupView.as_view(), name='merchant-signup'),
    path('internal/merchant-subscription/', MerchantSubscriptionView.as_view(), name='merchant-subscription'),
    path('internal/merchant-leads/', MerchantLeadInternalListView.as_view(), name='internal-merchant-leads'),
    path('admin/tracking/merchant-leads/', MerchantLeadListView.as_view(), name='merchant-leads'),
    path('admin/merchants/', MerchantLeadListView.as_view(), name='admin-merchants'),
    path('admin/merchants/<str:merchant_id>/', MerchantLeadDetailView.as_view(), name='admin-merchant-detail'),
]