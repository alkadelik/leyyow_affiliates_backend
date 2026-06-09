import hashlib
import secrets

from django.utils.timezone import now, timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction, models
from django.db import models as db_models

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.backends import AffiliateJWTAuthentication
from accounts.models import Admin, Affiliate, AffiliateWallet, AffiliateTokenBlacklist, SystemSettings
from accounts.serializers import (
    AdminSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    AffiliateSerializer,
    AffiliateDetailSerializer,
    AffiliateListSerializer,
    CreateAffiliateSerializer,
    ValidateInviteSerializer,
    AffiliateRegisterSerializer,
    AffiliateLoginSerializer,
    AffiliateForgotPasswordSerializer,
    AffiliateResetPasswordSerializer,
    UpdateAffiliateStatusSerializer,
)
from accounts.permissions import IsAnyAdmin, IsAffiliate
from accounts.task import task_send_affiliate_welcome, task_send_affiliate_invite
from audit.utils import log_action
from django.db.models import Sum
from campaigns.models import CampaignAffiliate
from tracking.models import AffiliateLink, AffiliateCode, Conversion, Commission, LinkClick, MerchantLead

# ── Admin auth views ─────────────────────────────────────────────────────────

class AdminLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email    = serializer.validated_data['email'].lower().strip()
        password = serializer.validated_data['password']

        try:
            admin = Admin.objects.get(email=email)
        except Admin.DoesNotExist:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not admin.is_active:
            return Response({'detail': 'Account deactivated.'}, status=status.HTTP_403_FORBIDDEN)

        if not admin.check_password(password):
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        admin.last_login_at = now()
        admin.save(update_fields=['last_login_at'])

        log_action(
            actor_type='admin', actor_id=admin.id,
            action='admin.login', entity_type='admin', entity_id=admin.id,
        )

        refresh = RefreshToken.for_user(admin)
        return Response({
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
            'admin':   AdminSerializer(admin).data,
        })


class AdminLogoutView(APIView):
    permission_classes = [IsAnyAdmin]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response({'detail': 'Token is invalid or already blacklisted.'}, status=status.HTTP_400_BAD_REQUEST)

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action='admin.logout', entity_type='admin', entity_id=request.user.id,
        )
        return Response({'detail': 'Logged out successfully.'})


class AdminMeView(APIView):
    permission_classes = [IsAnyAdmin]

    def get(self, request):
        return Response(AdminSerializer(request.user).data)


class AdminForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower().strip()

        try:
            admin = Admin.objects.get(email=email, is_active=True)
        except Admin.DoesNotExist:
            return Response({'detail': 'If that email exists, a reset link has been sent.'})

        raw_token    = secrets.token_hex(32)
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        admin.password_reset_token      = hashed_token
        admin.password_reset_expires_at = now() + timedelta(hours=1)
        admin.save(update_fields=['password_reset_token', 'password_reset_expires_at'])

        reset_url = f"{settings.ADMIN_FRONTEND_URL}/reset-password?token={raw_token}"
        send_mail(
            subject='Reset your Leyyow password',
            message=f'Click the link below to reset your password. It expires in 1 hour.\n\n{reset_url}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[admin.email],
            fail_silently=False,
        )

        return Response({'detail': 'If that email exists, a reset link has been sent.'})


class AdminResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        raw_token    = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        try:
            admin = Admin.objects.get(password_reset_token=hashed_token)
        except Admin.DoesNotExist:
            return Response({'detail': 'Invalid reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        if admin.password_reset_expires_at < now():
            return Response({'detail': 'Reset link has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        admin.set_password(new_password)
        admin.password_reset_token      = None
        admin.password_reset_expires_at = None
        admin.save(update_fields=['password', 'password_reset_token', 'password_reset_expires_at'])

        log_action(
            actor_type='admin', actor_id=admin.id,
            action='admin.password_reset', entity_type='admin', entity_id=admin.id,
        )
        return Response({'detail': 'Password reset successfully.'})


# ── Affiliate admin management views ─────────────────────────────────────────

class CreateAffiliateView(APIView):
    permission_classes = [IsAnyAdmin]

    def post(self, request):
        serializer = CreateAffiliateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email     = serializer.validated_data['email']
        full_name = serializer.validated_data['full_name']

        raw_token    = secrets.token_hex(32)
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        affiliate = Affiliate.objects.create_user(
            email=email,
            full_name=full_name,
            created_by=request.user,
            status='invited',
            invite_token=hashed_token,
            invite_expires_at=now() + timedelta(days=7),
        )

        invite_url = f"{settings.AFFILIATE_FRONTEND_URL}/register?token={raw_token}"
        task_send_affiliate_invite.delay(str(affiliate.id), invite_url)

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action='affiliate.created', entity_type='affiliate', entity_id=affiliate.id,
        )

        return Response(AffiliateSerializer(affiliate).data, status=status.HTTP_201_CREATED)


class AffiliateListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAnyAdmin]

    def get(self, request):
        affiliates = Affiliate.objects.select_related('wallet').prefetch_related('campaign_affiliates', 'leads').order_by('-created_at')

        # Assignable filter — only registered affiliates (for campaign assignment dropdown)
        if request.query_params.get('assignable') == 'true':
            affiliates = affiliates.filter(status__in=['inactive', 'active'])

        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            affiliates = affiliates.filter(status=status_filter)

        # Search by name or email
        search = request.query_params.get('search')
        if search:
            affiliates = affiliates.filter(
                models.Q(full_name__icontains=search) |
                models.Q(email__icontains=search)
            )

        serializer = AffiliateListSerializer(affiliates, many=True)
        return Response({
            'count':   affiliates.count(),
            'results': serializer.data,
        })


class AffiliateDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAnyAdmin]

    def get(self, request, affiliate_id):
        try:
            affiliate = Affiliate.objects.select_related('wallet').prefetch_related(
                'bank_accounts', 'payout_requests'
            ).get(id=affiliate_id)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Affiliate not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AffiliateDetailSerializer(affiliate)
        return Response(serializer.data)


class AffiliateStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def patch(self, request, affiliate_id):
        try:
            affiliate = Affiliate.objects.get(id=affiliate_id)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Affiliate not found.'}, status=status.HTTP_404_NOT_FOUND)

        is_active = request.data.get('is_active')
        if is_active is None:
            return Response({'detail': 'is_active is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not is_active:
            # Deactivate — remove from all active campaigns
            from campaigns.models import CampaignAffiliate
            CampaignAffiliate.objects.filter(
                affiliate=affiliate,
                removed_at__isnull=True,
                campaign__status='active',
            ).update(removed_at=now())
            affiliate.status         = 'deactivated'
            affiliate.deactivated_at = now()
            affiliate.deactivated_by = request.user
            affiliate.save(update_fields=['status', 'deactivated_at', 'deactivated_by'])
        else:
            # Reactivate — clear deactivation fields, restore appropriate status
            from campaigns.models import CampaignAffiliate
            has_active_campaign = CampaignAffiliate.objects.filter(
                affiliate=affiliate,
                removed_at__isnull=True,
                campaign__status='active',
            ).exists()
            affiliate.status         = 'active' if has_active_campaign else 'inactive'
            affiliate.deactivated_at = None
            affiliate.deactivated_by = None
            affiliate.save(update_fields=['status', 'deactivated_at', 'deactivated_by'])

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action='affiliate.deactivated' if not is_active else 'affiliate.activated',
            entity_type='affiliate', entity_id=affiliate.id,
        )

        return Response({'status': affiliate.status})


class ResendInviteView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAnyAdmin]

    def post(self, request, affiliate_id):
        try:
            affiliate = Affiliate.objects.get(id=affiliate_id)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Affiliate not found.'}, status=status.HTTP_404_NOT_FOUND)

        if affiliate.status == 'active':
            return Response({'detail': 'Affiliate has already registered.'}, status=status.HTTP_400_BAD_REQUEST)

        if affiliate.status == 'deactivated':
            return Response({'detail': 'Cannot resend invite to a deactivated affiliate.'}, status=status.HTTP_400_BAD_REQUEST)

        raw_token    = secrets.token_hex(32)
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        affiliate.invite_token      = hashed_token
        affiliate.invite_expires_at = now() + timedelta(days=7)
        affiliate.save(update_fields=['invite_token', 'invite_expires_at'])

        invite_url = f"{settings.AFFILIATE_FRONTEND_URL}/register?token={raw_token}"
        task_send_affiliate_invite.delay(str(affiliate.id), invite_url)

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action='affiliate.invite_resent', entity_type='affiliate',
            entity_id=affiliate.id,
        )
        return Response({'detail': 'Invite resent successfully.'})

# ── Affiliate auth views ──────────────────────────────────────────────────────

def get_affiliate_tokens(affiliate):
    refresh = RefreshToken()
    refresh['user_id'] = str(affiliate.id)
    refresh['user_type'] = 'affiliate'
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class ValidateInviteView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raw_token = request.query_params.get('token')
        if not raw_token:
            return Response({'detail': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        try:
            affiliate = Affiliate.objects.get(invite_token=hashed_token)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Invalid invite link.'}, status=status.HTTP_400_BAD_REQUEST)

        if affiliate.status == 'inactive':
            return Response({'detail': 'This account has been deactivated.'}, status=status.HTTP_403_FORBIDDEN)

        if affiliate.invite_expires_at < now():
            return Response({'detail': 'Invite link has expired. Please contact Leyyow.'}, status=status.HTTP_400_BAD_REQUEST)

        if affiliate.status == 'active':
            return Response({'detail': 'You have already registered. Please log in.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'email':     affiliate.email,
            'full_name': affiliate.full_name,
        })


class AffiliateRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AffiliateRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        raw_token    = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        try:
            affiliate = Affiliate.objects.get(invite_token=hashed_token)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Invalid invite link.'}, status=status.HTTP_400_BAD_REQUEST)

        if affiliate.status == 'inactive':
            return Response({'detail': 'This account has been deactivated.'}, status=status.HTTP_403_FORBIDDEN)

        if affiliate.invite_expires_at < now():
            return Response({'detail': 'Invite link has expired. Please contact Leyyow.'}, status=status.HTTP_400_BAD_REQUEST)

        if affiliate.status == 'active':
            return Response({'detail': 'You have already registered. Please log in.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            affiliate.set_password(new_password)
            affiliate.status            = 'inactive'
            affiliate.registered_at     = now()
            affiliate.invite_token      = None
            affiliate.invite_expires_at = None
            affiliate.save(update_fields=[
                'password', 'status', 'registered_at',
                'invite_token', 'invite_expires_at',
            ])
            AffiliateWallet.objects.create(affiliate=affiliate)
            task_send_affiliate_welcome.delay(str(affiliate.id))

        log_action(
            actor_type='affiliate', actor_id=affiliate.id,
            action='affiliate.registered', entity_type='affiliate', entity_id=affiliate.id,
        )

        tokens = get_affiliate_tokens(affiliate)
        return Response({
            'access':    tokens['access'],
            'refresh':   tokens['refresh'],
            'affiliate': AffiliateSerializer(affiliate).data,
        }, status=status.HTTP_201_CREATED)


class AffiliateLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AffiliateLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email    = serializer.validated_data['email'].lower().strip()
        password = serializer.validated_data['password']

        try:
            affiliate = Affiliate.objects.get(email=email)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        if affiliate.status == 'invited':
            return Response({'detail': 'Please complete your registration using the invite link sent to your email.'}, status=status.HTTP_403_FORBIDDEN)

        if affiliate.status == 'inactive':
            return Response({'detail': 'Your account has been deactivated. Please contact Leyyow.'}, status=status.HTTP_403_FORBIDDEN)

        if not affiliate.check_password(password):
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)

        affiliate.last_login_at = now()
        affiliate.save(update_fields=['last_login_at'])

        log_action(
            actor_type='affiliate', actor_id=affiliate.id,
            action='affiliate.login', entity_type='affiliate', entity_id=affiliate.id,
        )

        tokens = get_affiliate_tokens(affiliate)
        return Response({
            'access':    tokens['access'],
            'refresh':   tokens['refresh'],
            'affiliate': AffiliateSerializer(affiliate).data,
        })


class AffiliateLogoutView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes = [IsAffiliate]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            jti = token['jti']
            AffiliateTokenBlacklist.objects.get_or_create(token_jti=jti)
        except TokenError:
            return Response({'detail': 'Token is invalid.'}, status=status.HTTP_400_BAD_REQUEST)

        log_action(
            actor_type='affiliate', actor_id=request.user.id,
            action='affiliate.logout', entity_type='affiliate', entity_id=request.user.id,
        )
        return Response({'detail': 'Logged out successfully.'})

class AffiliateMeView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes = [IsAffiliate]

    def get(self, request):
        return Response(AffiliateSerializer(request.user).data)


class AffiliateForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AffiliateForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email'].lower().strip()

        try:
            affiliate = Affiliate.objects.get(email=email, status='active')
        except Affiliate.DoesNotExist:
            return Response({'detail': 'If that email exists, a reset link has been sent.'})

        raw_token    = secrets.token_hex(32)
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        affiliate.password_reset_token      = hashed_token
        affiliate.password_reset_expires_at = now() + timedelta(hours=1)
        affiliate.save(update_fields=['password_reset_token', 'password_reset_expires_at'])

        reset_url = f"{settings.AFFILIATE_FRONTEND_URL}/reset-password?token={raw_token}"
        send_mail(
            subject='Reset your Leyyow password',
            message=f'Click the link below to reset your password. It expires in 1 hour.\n\n{reset_url}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[affiliate.email],
            fail_silently=False,
        )

        return Response({'detail': 'If that email exists, a reset link has been sent.'})


class AffiliateResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AffiliateResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        raw_token    = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        try:
            affiliate = Affiliate.objects.get(password_reset_token=hashed_token)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Invalid reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        if affiliate.password_reset_expires_at < now():
            return Response({'detail': 'Reset link has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        affiliate.set_password(new_password)
        affiliate.password_reset_token      = None
        affiliate.password_reset_expires_at = None
        affiliate.save(update_fields=['password', 'password_reset_token', 'password_reset_expires_at'])

        log_action(
            actor_type='affiliate', actor_id=affiliate.id,
            action='affiliate.password_reset', entity_type='affiliate', entity_id=affiliate.id,
        )
        return Response({'detail': 'Password reset successfully.'})
    
# ── Affiliate portal views ────────────────────────────────────────────────────

class AffiliateDashboardView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        affiliate = request.user

        # Wallet
        try:
            wallet = affiliate.wallet
            balance        = wallet.balance
            total_earned   = wallet.total_earned
            total_withdrawn = wallet.total_withdrawn
        except Exception:
            balance = total_earned = total_withdrawn = 0

        # Active campaigns
        from campaigns.models import CampaignAffiliate
        active_campaign_ids = CampaignAffiliate.objects.filter(
            affiliate   = affiliate,
            removed_at__isnull = True,
            campaign__status   = 'active',
        ).values_list('campaign_id', flat=True)

        active_campaigns = len(active_campaign_ids)

        # Totals
        from tracking.models import Conversion, Commission, LinkClick
        total_conversions = Conversion.objects.filter(affiliate=affiliate).count()
        total_clicks      = LinkClick.objects.filter(
            affiliate   = affiliate,
            is_duplicate = False,
        ).count()

        total_signups = MerchantLead.objects.filter(
            affiliate=request.user,
        ).count()

        # Recent commissions — last 5
        recent = Commission.objects.filter(
            affiliate = affiliate,
            status    = 'earned',
        ).select_related('campaign', 'conversion').order_by('-earned_at')[:5]

        recent_commissions = [
            {
                'id':            str(c.id),
                'amount':        c.amount,
                'campaign_name': c.campaign.name,
                'merchant_name': c.conversion.merchant_name,
                'earned_at':     c.earned_at.isoformat(),
            }
            for c in recent
        ]

        return Response({
            'full_name':          affiliate.full_name,
            'wallet_balance':     balance,
            'total_earned':       total_earned,
            'total_withdrawn':    total_withdrawn,
            'active_campaigns':   active_campaigns,
            'total_conversions':  total_conversions,
            'total_clicks':       total_clicks,
            'total_signups': total_signups,
            'recent_commissions': recent_commissions,
        })


class AffiliateCampaignListView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        from campaigns.models import CampaignAffiliate
        from tracking.models import AffiliateLink, AffiliateCode, Conversion, Commission, LinkClick

        assignments = CampaignAffiliate.objects.filter(
            affiliate  = request.user,
            removed_at__isnull = True,
        ).select_related('campaign').order_by('-assigned_at')

        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            assignments = assignments.filter(campaign__status=status_filter)

        results = []
        for ca in assignments:
            campaign = ca.campaign

            # Link
            try:
                link = ca.link
                link_data = {
                    'id':          str(link.id),
                    'slug':        link.slug,
                    'full_url':    link.full_url,
                    'click_count': link.click_count,
                }
            except Exception:
                link_data = None

            # Code
            try:
                code = ca.code
                code_data = {
                    'id':        str(code.id),
                    'code':      code.code,
                    'is_custom': code.is_custom,
                    'use_count': code.use_count,
                }
            except Exception:
                code_data = None

            # Stats
            total_conversions = Conversion.objects.filter(
                affiliate = request.user,
                campaign  = campaign,
            ).count()

            total_earned = Commission.objects.filter(
                affiliate = request.user,
                campaign  = campaign,
                status    = 'earned',
            ).aggregate(
                total=models.Sum('amount')
            )['total'] or 0

            total_clicks = LinkClick.objects.filter(
                affiliate    = request.user,
                campaign     = campaign,
                is_duplicate = False,
            ).count()

            results.append({
                'id':                  str(campaign.id),
                'name':                campaign.name,
                'description':         campaign.description,
                'status':              campaign.status,
                'commission_type':     campaign.commission_type,
                'commission_value':    campaign.commission_value,
                'commission_cap':      campaign.commission_cap,
                'tier':                campaign.tier,
                'starts_at':           campaign.starts_at.isoformat() if campaign.starts_at else None,
                'ends_at':             campaign.ends_at.isoformat() if campaign.ends_at else None,
                'terms_and_conditions': campaign.terms_and_conditions,
                'link':                link_data,
                'code':                code_data,
                'total_clicks':        total_clicks,
                'total_conversions':   total_conversions,
                'total_earned':        total_earned,
            })

        return Response({'count': len(results), 'results': results})


class AffiliateCampaignDetailView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request, campaign_id):
        try:
            ca = CampaignAffiliate.objects.select_related('campaign').get(
                affiliate  = request.user,
                campaign_id = campaign_id,
                removed_at__isnull = True,
            )
        except CampaignAffiliate.DoesNotExist:
            return Response({'detail': 'Campaign not found.'}, status=status.HTTP_404_NOT_FOUND)

        campaign = ca.campaign

        # Link
        try:
            link = ca.link
            link_data = {
                'id':          str(link.id),
                'slug':        link.slug,
                'full_url':    link.full_url,
                'click_count': link.click_count,
            }
        except Exception:
            link_data = None

        # Code
        try:
            code = ca.code
            code_data = {
                'id':        str(code.id),
                'code':      code.code,
                'is_custom': code.is_custom,
                'use_count': code.use_count,
            }
        except Exception:
            code_data = None

        # Commission history
        commissions = Commission.objects.filter(
            affiliate = request.user,
            campaign  = campaign,
        ).select_related('conversion').order_by('-earned_at')[:20]

        commission_history = [
            {
                'id':            str(c.id),
                'status':        c.status,
                'amount':        c.amount,
                'payment_amount': c.payment_amount,
                'merchant_name': c.conversion.merchant_name,
                'earned_at':     c.earned_at.isoformat(),
            }
            for c in commissions
        ]

        # Stats
        total_signups = MerchantLead.objects.filter(
            affiliate=request.user,
            campaign=campaign,
        ).count()

        total_conversions = Conversion.objects.filter(
            affiliate = request.user,
            campaign  = campaign,
        ).count()

        total_earned = Commission.objects.filter(
            affiliate = request.user,
            campaign  = campaign,
            status    = 'earned',
        ).aggregate(total=models.Sum('amount'))['total'] or 0

        total_clicks = LinkClick.objects.filter(
            affiliate    = request.user,
            campaign     = campaign,
            is_duplicate = False,
        ).count()

        return Response({
            'id':                  str(campaign.id),
            'name':                campaign.name,
            'description':         campaign.description,
            'status':              campaign.status,
            'commission_type':     campaign.commission_type,
            'commission_value':    campaign.commission_value,
            'commission_cap':      campaign.commission_cap,
            'tier':                campaign.tier,
            'starts_at':           campaign.starts_at.isoformat() if campaign.starts_at else None,
            'ends_at':             campaign.ends_at.isoformat() if campaign.ends_at else None,
            'terms_and_conditions': campaign.terms_and_conditions,
            'link':                link_data,
            'code':                code_data,
            'total_clicks':        total_clicks,
            'total_conversions':   total_conversions,
            'total_earned':        total_earned,
            'commission_history':  commission_history,
            'total_signups': total_signups,
        })


class AffiliateProfileView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        from accounts.serializers import AffiliateProfileSerializer
        return Response(AffiliateProfileSerializer(request.user).data)

    def patch(self, request):
        from accounts.serializers import UpdateAffiliateProfileSerializer
        serializer = UpdateAffiliateProfileSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        request.user.full_name = serializer.validated_data['full_name']
        request.user.save(update_fields=['full_name', 'updated_at'])

        log_action(
            actor_type='affiliate', actor_id=request.user.id,
            action='affiliate.profile_updated', entity_type='affiliate',
            entity_id=request.user.id,
        )

        from accounts.serializers import AffiliateProfileSerializer
        return Response(AffiliateProfileSerializer(request.user).data)


class AffiliateChangePasswordView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def post(self, request):
        from accounts.serializers import ChangeAffiliatePasswordSerializer
        serializer = ChangeAffiliatePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        current_password = serializer.validated_data['current_password']
        new_password     = serializer.validated_data['new_password']

        if not request.user.check_password(current_password):
            return Response(
                {'detail': 'Current password is incorrect.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if current_password == new_password:
            return Response(
                {'detail': 'New password must be different from current password.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=['password', 'updated_at'])

        log_action(
            actor_type='affiliate', actor_id=request.user.id,
            action='affiliate.password_changed', entity_type='affiliate',
            entity_id=request.user.id,
        )

        return Response({'detail': 'Password changed successfully.'})


class AffiliateCommissionListView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        from tracking.models import Commission
        commissions = Commission.objects.filter(
            affiliate = request.user,
        ).select_related('campaign', 'conversion').order_by('-earned_at')

        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            commissions = commissions.filter(status=status_filter)

        # Filter by campaign
        campaign_id = request.query_params.get('campaign_id')
        if campaign_id:
            commissions = commissions.filter(campaign_id=campaign_id)

        results = [
            {
                'id':                      str(c.id),
                'status':                  c.status,
                'amount':                  c.amount,
                'payment_amount':          c.payment_amount,
                'commission_type_snapshot': c.commission_type_snapshot,
                'campaign_name':           c.campaign.name,
                'merchant_name':           c.conversion.merchant_name,
                'earned_at':               c.earned_at.isoformat(),
                'reversed_at':             c.reversed_at.isoformat() if c.reversed_at else None,
            }
            for c in commissions
        ]

        return Response({'count': len(results), 'results': results})
    

class AffiliateMerchantListView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        from tracking.models import MerchantLead, Conversion, Commission
        from django.db import models as db_models

        leads = MerchantLead.objects.filter(
            affiliate=request.user,
        ).select_related('campaign').order_by('-signed_up_at')

        search = request.query_params.get('search')
        if search:
            leads = leads.filter(merchant_name__icontains=search)

        results = []
        for lead in leads:
            conversion = Conversion.objects.filter(
                affiliate=request.user,
                merchant_id=lead.merchant_id,
            ).first()

            is_subscribed = conversion is not None

            if conversion:
                attribution_source = conversion.attribution_source
                # src = conversion.attribution_source
                # attribution_source = 'affiliate_code' if src in ('affiliate_code', 'coupon_code') else 'affiliate_link'
            else:
                attribution_source = 'affiliate_code' if lead.affiliate_code_id else 'affiliate_link'

            total_earned = Commission.objects.filter(
                affiliate=request.user,
                conversion__merchant_id=lead.merchant_id,
                status='earned',
            ).aggregate(total=db_models.Sum('amount'))['total'] or 0

            commission_count = Commission.objects.filter(
                affiliate=request.user,
                conversion__merchant_id=lead.merchant_id,
            ).count()

            results.append({
                'merchant_id':        lead.merchant_id,
                'merchant_name':      lead.merchant_name,
                'campaign_id':        str(lead.campaign.id),
                'campaign_name':      lead.campaign.name,
                'attribution_source': attribution_source,
                'referred_at':        lead.signed_up_at.isoformat(),
                'is_subscribed':      is_subscribed,
                'total_earned':       total_earned,
                'commission_count':   commission_count,
            })

        return Response({'count': len(results), 'results': results})


class AffiliateMerchantDetailView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request, merchant_id):
        # Verify this merchant was referred by this affiliate
        conversion = Conversion.objects.filter(
            affiliate   = request.user,
            merchant_id = merchant_id,
        ).select_related('campaign', 'affiliate_link', 'affiliate_code').first()

        if not conversion:
            return Response(
                {'detail': 'Merchant not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # All commissions from this merchant
        commissions = Commission.objects.filter(
            affiliate  = request.user,
            conversion__merchant_id = merchant_id,
        ).select_related('conversion').order_by('-earned_at')

        commission_history = [
            {
                'id':            str(c.id),
                'status':        c.status,
                'amount':        c.amount,
                'payment_amount': c.payment_amount,
                'commission_type_snapshot': c.commission_type_snapshot,
                'earned_at':     c.earned_at.isoformat(),
                'reversed_at':   c.reversed_at.isoformat() if c.reversed_at else None,
            }
            for c in commissions
        ]

        # Totals
        total_earned = commissions.filter(
            status='earned'
        ).aggregate(
            total=db_models.Sum('amount')
        )['total'] or 0

        total_reversed = commissions.filter(
            status='reversed'
        ).aggregate(
            total=db_models.Sum('amount')
        )['total'] or 0

        # Attribution detail
        attribution = {
            'source': conversion.attribution_source,
            'link_url': conversion.affiliate_link.full_url if conversion.affiliate_link else None,
            'code':     conversion.affiliate_code.code if conversion.affiliate_code else None,
        }

        return Response({
            'merchant_id':        merchant_id,
            'merchant_name':      conversion.merchant_name,
            'campaign_name':      conversion.campaign.name,
            'campaign_id':        str(conversion.campaign.id),
            'referred_at':        conversion.registration_at.isoformat(),
            'attribution':        attribution,
            'total_earned':       total_earned,
            'total_reversed':     total_reversed,
            'net_earned':         total_earned - total_reversed,
            'commission_history': commission_history,
        })
    

class AffiliateTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes     = []

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            # Verify this is an affiliate token
            if token.get('user_type') != 'affiliate':
                return Response({'detail': 'Invalid token.'}, status=status.HTTP_401_UNAUTHORIZED)
            return Response({'access': str(token.access_token)})
        except Exception:
            return Response({'detail': 'Invalid or expired refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)


class AdminTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes     = []

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            return Response({'access': str(token.access_token)})
        except Exception:
            return Response({'detail': 'Invalid or expired refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)
        

class AffiliateCampaignHistoryView(APIView):
    """List campaigns an affiliate has been assigned to — admin side."""
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request, affiliate_id):
        try:
            affiliate = Affiliate.objects.get(id=affiliate_id)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Affiliate not found.'}, status=status.HTTP_404_NOT_FOUND)

        assignments = CampaignAffiliate.objects.filter(
            affiliate=affiliate
        ).select_related('campaign')

        data = []
        for ca in assignments:
            campaign = ca.campaign

            total_earned = Commission.objects.filter(
                affiliate=affiliate, campaign=campaign, status='earned'
            ).aggregate(total=Sum('amount'))['total'] or 0

            total_leads = MerchantLead.objects.filter(
                affiliate=affiliate, campaign=campaign
            ).count()

            total_conversions = MerchantLead.objects.filter(
                affiliate=affiliate, campaign=campaign, status='subscribed'
            ).count()

            total_sales = MerchantLead.objects.filter(
                affiliate=affiliate, campaign=campaign, status='subscribed'
            ).aggregate(total=Sum('amount_paid_kobo'))['total'] or 0

            conversion_rate = (
                round(total_conversions / total_leads * 100, 2)
                if total_leads > 0 else None
            )

            roi = (
                round((total_earned / total_sales) * 100, 2)
                if total_sales > 0 else None
            )

            data.append({
                'campaign_id':      str(campaign.id),
                'campaign_name':    campaign.name,
                'status':           campaign.status,
                'total_earned':     total_earned,
                'total_sales':      total_sales,
                'conversion_count': total_conversions,
                'conversion_rate':  conversion_rate,
                'roi':              roi,
                'start_date':       campaign.starts_at,
                'end_date':         campaign.ends_at,
            })

        return Response({'count': len(data), 'results': data})


class SystemSettingsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        s = SystemSettings.get()
        return Response({
            'payout_auto_approve':     s.payout_auto_approve,
            'minimum_withdrawal_kobo': s.minimum_withdrawal_kobo,
            'tracking_base_url':       s.tracking_base_url,
        })

    def patch(self, request):
        s = SystemSettings.get()
        allowed = {'payout_auto_approve', 'minimum_withdrawal_kobo', 'tracking_base_url'}
        fields_to_save = []
        for field in allowed:
            if field in request.data:
                setattr(s, field, request.data[field])
                fields_to_save.append(field)
        if fields_to_save:
            s.save(update_fields=fields_to_save)
        return Response({
            'payout_auto_approve':     s.payout_auto_approve,
            'minimum_withdrawal_kobo': s.minimum_withdrawal_kobo,
            'tracking_base_url':       s.tracking_base_url,
        })