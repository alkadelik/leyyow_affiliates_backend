from django.urls import path
from payouts.views import (
    BankAccountListView,
    BankAccountDetailView,
    AffiliateWalletView,
    PayoutRequestListView,
    AdminPayoutListView,
    AdminPayoutDetailView,
    AdminCentralWalletView,
    AdminWalletManagementView,
    PaystackWebhookView,
    BankListView,
    ResolveAccountView,
)

urlpatterns = [
    # Affiliate
    path('affiliate/wallet/', AffiliateWalletView.as_view(),     name='affiliate-wallet'),
    path('affiliate/bank-accounts/', BankAccountListView.as_view(),     name='bank-account-list'),
    path('affiliate/bank-accounts/<uuid:account_id>/', BankAccountDetailView.as_view(), name='bank-account-detail'),
    path('affiliate/payouts/', PayoutRequestListView.as_view(),   name='affiliate-payouts'),

    # Admin
    path('admin/payouts/', AdminPayoutListView.as_view(),     name='admin-payout-list'),
    path('admin/payouts/<uuid:payout_id>/', AdminPayoutDetailView.as_view(),   name='admin-payout-detail'),
    path('admin/wallet/', AdminCentralWalletView.as_view(),  name='admin-central-wallet'),

    # Payments
    path('payouts/webhook/paystack/', PaystackWebhookView.as_view(), name='paystack-webhook'),
    path('banks/', BankListView.as_view()),
    path('banks/resolve/', ResolveAccountView.as_view()),
    path('affiliate/banks/', BankListView.as_view(),     name='bank-list'),
    path('affiliate/banks/resolve/', ResolveAccountView.as_view(), name='bank-resolve'),
    path('admin/wallet/management/', AdminWalletManagementView.as_view(), name='admin-wallet-management'),
]