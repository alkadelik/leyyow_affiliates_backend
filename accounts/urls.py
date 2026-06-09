from django.urls import path
from accounts.views import (
    AdminLoginView,
    AdminLogoutView,
    AdminMeView,
    AdminForgotPasswordView,
    AdminResetPasswordView,
    CreateAffiliateView,
    AffiliateListView,
    AffiliateDetailView,
    AffiliateStatusView,
    ResendInviteView,
    ValidateInviteView,
    AffiliateRegisterView,
    AffiliateLoginView,
    AffiliateLogoutView,
    AffiliateMeView,
    AffiliateForgotPasswordView,
    AffiliateResetPasswordView,
    AffiliateDashboardView,
    AffiliateCampaignListView,
    AffiliateCampaignDetailView,
    AffiliateProfileView,
    AffiliateChangePasswordView,
    AffiliateCommissionListView,
    AffiliateMerchantListView,
    AffiliateMerchantDetailView,
    AffiliateTokenRefreshView,
    AdminTokenRefreshView,
    AffiliateCampaignHistoryView,
    SystemSettingsView,
)

urlpatterns = [
    # Admin auth
    path('admin/auth/login/', AdminLoginView.as_view(), name='admin-login'),
    path('admin/auth/logout/', AdminLogoutView.as_view(), name='admin-logout'),
    path('admin/auth/me/', AdminMeView.as_view(), name='admin-me'),
    path('admin/auth/forgot-password/', AdminForgotPasswordView.as_view(), name='admin-forgot-password'),
    path('admin/auth/reset-password/', AdminResetPasswordView.as_view(),  name='admin-reset-password'),
    path('admin/auth/token/refresh/', AdminTokenRefreshView.as_view(), name='admin-token-refresh'),

    # Admin managing affiliates
    path('admin/affiliates/create/', CreateAffiliateView.as_view(), name='affiliate-create'),
    path('admin/affiliates/', AffiliateListView.as_view(), name='affiliate-list'),
    path('admin/affiliates/<uuid:affiliate_id>/', AffiliateDetailView.as_view(), name='affiliate-detail'),
    path('admin/affiliates/<uuid:affiliate_id>/status/', AffiliateStatusView.as_view(), name='affiliate-status'),
    path('admin/affiliates/<uuid:affiliate_id>/resend-invite/', ResendInviteView.as_view(), name='affiliate-resend-invite'),
    path('admin/affiliates/<uuid:affiliate_id>/campaigns/', AffiliateCampaignHistoryView.as_view(), name='affiliate-campaigns-history'),

    # Affiliate auth
    path('affiliate/auth/invite/', ValidateInviteView.as_view(),          name='affiliate-invite-validate'),
    path('affiliate/auth/register/', AffiliateRegisterView.as_view(),       name='affiliate-register'),
    path('affiliate/auth/login/', AffiliateLoginView.as_view(), name='affiliate-login'),
    path('affiliate/auth/logout/', AffiliateLogoutView.as_view(),         name='affiliate-logout'),
    path('affiliate/auth/me/', AffiliateMeView.as_view(), name='affiliate-me'),
    path('affiliate/auth/forgot-password/', AffiliateForgotPasswordView.as_view(), name='affiliate-forgot-password'),
    path('affiliate/auth/reset-password/', AffiliateResetPasswordView.as_view(),  name='affiliate-reset-password'),
    path('affiliate/auth/token/refresh/', AffiliateTokenRefreshView.as_view(), name='affiliate-token-refresh'),

    # Affiliate portal
    path('affiliate/dashboard/', AffiliateDashboardView.as_view(),      name='affiliate-dashboard'),
    path('affiliate/campaigns/', AffiliateCampaignListView.as_view(),   name='affiliate-campaigns'),
    path('affiliate/campaigns/<uuid:campaign_id>/', AffiliateCampaignDetailView.as_view(), name='affiliate-campaign-detail'),
    path('affiliate/profile/', AffiliateProfileView.as_view(), name='affiliate-profile'),
    path('affiliate/profile/change-password/', AffiliateChangePasswordView.as_view(), name='affiliate-change-password'),
    path('affiliate/commissions/', AffiliateCommissionListView.as_view(), name='affiliate-commissions'),

    # Affiliate Merchants
    path('affiliate/merchants/', AffiliateMerchantListView.as_view(),   name='affiliate-merchants'),
    path('affiliate/merchants/<str:merchant_id>/', AffiliateMerchantDetailView.as_view(), name='affiliate-merchant-detail'),

    # Admin Settings
    path('admin/settings/', SystemSettingsView.as_view(), name='admin-settings'),
]