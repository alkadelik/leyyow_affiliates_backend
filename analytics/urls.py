from django.urls import path
from analytics.views import (
    AdminOverviewAnalyticsView,
    AdminCampaignAnalyticsView,
    AffiliateEarningsAnalyticsView,
    AdminAffiliateAnalyticsView,
)

urlpatterns = [
    # Admin
    path('admin/analytics/', AdminOverviewAnalyticsView.as_view(), name='admin-analytics'),
    path('admin/analytics/campaigns/<uuid:campaign_id>/', AdminCampaignAnalyticsView.as_view(), name='admin-campaign-analytics'),
    path('admin/analytics/affiliates/<uuid:affiliate_id>/', AdminAffiliateAnalyticsView.as_view(), name='admin-affiliate-analytics'),

    # Affiliate
    path('affiliate/analytics/', AffiliateEarningsAnalyticsView.as_view(), name='affiliate-analytics'),
]