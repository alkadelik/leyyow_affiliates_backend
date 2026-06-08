from django.urls import path
from campaigns.views import (
    CampaignListView,
    CampaignDetailView,
    CampaignTransitionView,
    CampaignAffiliateView,
)

urlpatterns = [
    path('', CampaignListView.as_view(), name='campaign-list'),
    path('<uuid:campaign_id>/', CampaignDetailView.as_view(), name='campaign-detail'),
    path('<uuid:campaign_id>/transition/', CampaignTransitionView.as_view(), name='campaign-transition'),
    path('<uuid:campaign_id>/affiliates/', CampaignAffiliateView.as_view(), name='campaign-affiliates'),
]