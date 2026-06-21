from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Admin, Affiliate, AffiliateWallet
from campaigns.models import Campaign, CampaignAffiliate
from tracking.models import AffiliateCode, Conversion, Commission, CentralWallet


def _make_admin():
    return Admin.objects.create_user(
        email='admin@leyyow.com',
        full_name='Admin',
        password='pass',
    )


def _make_campaign(admin):
    return Campaign.objects.create(
        name='Test Campaign',
        status='active',
        commission_type='flat_fee',
        commission_value=5000,
        commission_trigger='first_subscription_only',
        created_by=admin,
    )


def _make_affiliate(admin, campaign):
    affiliate = Affiliate.objects.create_user(
        email='affiliate@example.com',
        full_name='Jane Doe',
        password='pass',
        created_by=admin,
    )
    affiliate.status = 'active'
    affiliate.save()
    AffiliateWallet.objects.create(affiliate=affiliate)
    ca = CampaignAffiliate.objects.create(
        campaign=campaign,
        affiliate=affiliate,
        assigned_by=admin,
    )
    code = AffiliateCode.objects.create(
        campaign_affiliate=ca,
        campaign=campaign,
        affiliate=affiliate,
        code='JANE-TEST',
    )
    return affiliate, code


@override_settings(INTERNAL_API_SECRET='test-secret')
class ConversionFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _make_admin()
        self.campaign = _make_campaign(self.admin)
        self.affiliate, self.code = _make_affiliate(self.admin, self.campaign)
        CentralWallet.objects.create(id=1)

    def _post(self, payload, secret='test-secret'):
        return self.client.post(
            '/api/internal/conversions/',
            payload,
            format='json',
            HTTP_X_INTERNAL_SECRET=secret,
        )

    # --- Auth guard ---

    def test_missing_secret_forbidden(self):
        res = self.client.post('/api/internal/conversions/', {}, format='json')
        self.assertEqual(res.status_code, 403)

    def test_wrong_secret_forbidden(self):
        res = self._post({}, secret='wrong')
        self.assertEqual(res.status_code, 403)

    # --- Happy path: coupon code attribution ---

    def test_coupon_code_attribution_creates_commission(self):
        res = self._post({
            'merchant_subscription_id': 'sub-001',
            'merchant_id': 'merchant-001',
            'payment_amount': 100000,
            'coupon_code': 'JANE-TEST',
        })
        self.assertEqual(res.status_code, 201)

        # Commission created with correct flat fee amount
        commission = Commission.objects.get(conversion__merchant_subscription_id='sub-001')
        self.assertEqual(commission.amount, 5000)
        self.assertEqual(commission.status, 'earned')

        # Affiliate wallet credited
        wallet = AffiliateWallet.objects.get(affiliate=self.affiliate)
        self.assertEqual(wallet.balance, 5000)
        self.assertEqual(wallet.total_earned, 5000)

        # Central wallet credited
        central = CentralWallet.objects.get(id=1)
        self.assertEqual(central.balance, 5000)

        # Code use count incremented
        self.code.refresh_from_db()
        self.assertEqual(self.code.use_count, 1)

    # --- Duplicate prevention ---

    def test_duplicate_conversion_rejected(self):
        self._post({
            'merchant_subscription_id': 'sub-dup',
            'merchant_id': 'merchant-001',
            'payment_amount': 100000,
            'coupon_code': 'JANE-TEST',
        })
        res = self._post({
            'merchant_subscription_id': 'sub-dup',
            'merchant_id': 'merchant-001',
            'payment_amount': 100000,
            'coupon_code': 'JANE-TEST',
        })
        self.assertEqual(res.status_code, 409)
        self.assertEqual(
            Conversion.objects.filter(merchant_subscription_id='sub-dup').count(), 1
        )

    # --- Self-referral ---

    def test_self_referral_no_commission_issued(self):
        res = self._post({
            'merchant_subscription_id': 'sub-self',
            'merchant_id': str(self.affiliate.id),
            'payment_amount': 100000,
            'coupon_code': 'JANE-TEST',
        })
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            Commission.objects.filter(conversion__merchant_subscription_id='sub-self').exists()
        )

    # --- Unattributed ---

    def test_unattributed_no_conversion_or_commission(self):
        res = self._post({
            'merchant_subscription_id': 'sub-unattr',
            'merchant_id': 'merchant-999',
            'payment_amount': 100000,
            # no coupon_code, no session_fingerprint
        })
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            Conversion.objects.filter(merchant_subscription_id='sub-unattr').exists()
        )
        self.assertFalse(Commission.objects.exists())
