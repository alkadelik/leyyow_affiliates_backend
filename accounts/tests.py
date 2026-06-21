import hashlib
import secrets
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.timezone import now
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import Admin, Affiliate, AffiliateWallet
from accounts.views import get_affiliate_tokens


class AdminAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = Admin.objects.create_user(
            email='admin@leyyow.com',
            full_name='Test Admin',
            password='Str0ng#Pass!',
        )

    def _get_tokens(self):
        refresh = RefreshToken.for_user(self.admin)
        return str(refresh.access_token), str(refresh)

    def test_login_success(self):
        res = self.client.post('/api/admin/auth/login/', {
            'email': 'admin@leyyow.com',
            'password': 'Str0ng#Pass!',
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)
        self.assertIn('admin', res.data)

    def test_login_wrong_password(self):
        res = self.client.post('/api/admin/auth/login/', {
            'email': 'admin@leyyow.com',
            'password': 'wrong',
        })
        self.assertEqual(res.status_code, 401)

    def test_login_inactive_account(self):
        self.admin.is_active = False
        self.admin.save()
        res = self.client.post('/api/admin/auth/login/', {
            'email': 'admin@leyyow.com',
            'password': 'Str0ng#Pass!',
        })
        self.assertEqual(res.status_code, 403)

    def test_me_authenticated(self):
        access, _ = self._get_tokens()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        res = self.client.get('/api/admin/auth/me/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['email'], 'admin@leyyow.com')

    def test_me_unauthenticated(self):
        res = self.client.get('/api/admin/auth/me/')
        self.assertEqual(res.status_code, 401)

    def test_logout_blacklists_refresh_token(self):
        access, refresh = self._get_tokens()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        res = self.client.post('/api/admin/auth/logout/', {'refresh': refresh})
        self.assertEqual(res.status_code, 200)

        # Blacklisted token must not refresh
        self.client.credentials()
        res = self.client.post('/api/admin/auth/token/refresh/', {'refresh': refresh})
        self.assertEqual(res.status_code, 401)


class AffiliateAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = Admin.objects.create_user(
            email='admin@leyyow.com',
            full_name='Test Admin',
            password='pass',
        )

        # Invited affiliate — used for invite validation and register tests
        self.raw_invite_token = secrets.token_hex(32)
        self.invited = Affiliate.objects.create_user(
            email='invited@example.com',
            full_name='Invited User',
            created_by=self.admin,
        )
        self.invited.invite_token = hashlib.sha256(self.raw_invite_token.encode()).hexdigest()
        self.invited.invite_expires_at = now() + timedelta(days=7)
        self.invited.status = 'invited'
        self.invited.save()

        # Active affiliate — used for login and /me tests
        self.active = Affiliate.objects.create_user(
            email='active@example.com',
            full_name='Active User',
            password='Str0ng#Pass!',
            created_by=self.admin,
        )
        self.active.status = 'active'
        self.active.save()
        AffiliateWallet.objects.create(affiliate=self.active)

    # --- Invite validation ---

    def test_invite_valid_token(self):
        res = self.client.get(f'/api/affiliate/auth/invite/?token={self.raw_invite_token}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['email'], 'invited@example.com')

    def test_invite_expired_token(self):
        self.invited.invite_expires_at = now() - timedelta(days=1)
        self.invited.save()
        res = self.client.get(f'/api/affiliate/auth/invite/?token={self.raw_invite_token}')
        self.assertEqual(res.status_code, 400)

    def test_invite_already_registered(self):
        self.invited.status = 'active'
        self.invited.save()
        res = self.client.get(f'/api/affiliate/auth/invite/?token={self.raw_invite_token}')
        self.assertEqual(res.status_code, 400)

    # --- Registration ---

    @patch('accounts.views.task_send_affiliate_welcome.delay')
    def test_register_success(self, mock_task):
        res = self.client.post('/api/affiliate/auth/register/', {
            'token': self.raw_invite_token,
            'new_password': 'Str0ng#Pass!',
        })
        self.assertEqual(res.status_code, 201)
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)
        mock_task.assert_called_once()

    def test_register_expired_token(self):
        self.invited.invite_expires_at = now() - timedelta(days=1)
        self.invited.save()
        res = self.client.post('/api/affiliate/auth/register/', {
            'token': self.raw_invite_token,
            'new_password': 'Str0ng#Pass!',
        })
        self.assertEqual(res.status_code, 400)

    def test_register_invalid_token(self):
        res = self.client.post('/api/affiliate/auth/register/', {
            'token': 'completely-wrong-token',
            'new_password': 'Str0ng#Pass!',
        })
        self.assertEqual(res.status_code, 400)

    # --- Login ---

    def test_login_success(self):
        res = self.client.post('/api/affiliate/auth/login/', {
            'email': 'active@example.com',
            'password': 'Str0ng#Pass!',
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)

    def test_login_wrong_password(self):
        res = self.client.post('/api/affiliate/auth/login/', {
            'email': 'active@example.com',
            'password': 'wrong',
        })
        self.assertEqual(res.status_code, 401)

    def test_login_invited_status_blocked(self):
        res = self.client.post('/api/affiliate/auth/login/', {
            'email': 'invited@example.com',
            'password': 'any',
        })
        self.assertEqual(res.status_code, 403)

    def test_login_inactive_status_blocked(self):
        self.active.status = 'inactive'
        self.active.save()
        res = self.client.post('/api/affiliate/auth/login/', {
            'email': 'active@example.com',
            'password': 'Str0ng#Pass!',
        })
        self.assertEqual(res.status_code, 403)

    # --- /me ---

    def test_me_authenticated(self):
        tokens = get_affiliate_tokens(self.active)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
        res = self.client.get('/api/affiliate/auth/me/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['email'], 'active@example.com')

    def test_me_unauthenticated(self):
        res = self.client.get('/api/affiliate/auth/me/')
        self.assertEqual(res.status_code, 401)


class TokenIsolationTests(TestCase):
    """Admin tokens must be rejected on affiliate endpoints and vice versa."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = Admin.objects.create_user(
            email='admin@leyyow.com',
            full_name='Admin',
            password='pass',
        )
        self.affiliate = Affiliate.objects.create_user(
            email='aff@example.com',
            full_name='Affiliate',
            password='pass',
            created_by=self.admin,
        )
        self.affiliate.status = 'active'
        self.affiliate.save()
        AffiliateWallet.objects.create(affiliate=self.affiliate)

    def test_admin_token_rejected_on_affiliate_endpoint(self):
        admin_access = str(RefreshToken.for_user(self.admin).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_access}')
        res = self.client.get('/api/affiliate/auth/me/')
        self.assertEqual(res.status_code, 401)

    def test_affiliate_token_rejected_on_admin_endpoint(self):
        tokens = get_affiliate_tokens(self.affiliate)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
        res = self.client.get('/api/admin/auth/me/')
        self.assertEqual(res.status_code, 401)
