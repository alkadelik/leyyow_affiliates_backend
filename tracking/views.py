from django.http import HttpResponseRedirect
from django.utils.timezone import now
from django.db import transaction
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from rest_framework_simplejwt.authentication import JWTAuthentication

from tracking.models import AffiliateLink, AffiliateCode, Conversion, Commission, MerchantLead
from tracking.serializers import (
    AffiliateLinkSerializer,
    AffiliateCodeSerializer,
    UpdateAffiliateCodeSerializer,
    RecordConversionSerializer,
    ConversionSerializer,
    CommissionSerializer,
)
from tracking import attribution, commission as commission_engine
from tracking.central_wallet import credit_central_wallet
from campaigns.models import CampaignAffiliate
from accounts.models import Affiliate
from accounts.permissions import IsAnyAdmin, IsAffiliate
from accounts.backends import AffiliateJWTAuthentication
from audit.utils import log_action


class TrackClickView(APIView):
    """
    Public endpoint. Receives a slug, records the click, and
    redirects the visitor to the campaign landing page.
    GET /r/<slug>/
    """
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            affiliate_link = AffiliateLink.objects.select_related(
                'affiliate', 'campaign'
            ).get(slug=slug)
        except AffiliateLink.DoesNotExist:
            return Response({'detail': 'Link not found.'}, status=status.HTTP_404_NOT_FOUND)

        if affiliate_link.campaign.status != 'active':
            return Response({'detail': 'This campaign is no longer active.'}, status=status.HTTP_410_GONE)

        attribution.record_click(request, affiliate_link)

        # Redirect to campaign landing page
        redirect_url = getattr(settings, 'CAMPAIGN_LANDING_URL', 'https://leyyow.com')
        return HttpResponseRedirect(redirect_url)


class GenerateLinkAndCodeView(APIView):
    """
    Admin triggers link + code generation when assigning an affiliate to a campaign.
    Called automatically after CampaignAffiliateView.post() — or can be called manually.
    POST /api/admin/tracking/generate/
    """
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def post(self, request):
        campaign_affiliate_id = request.data.get('campaign_affiliate_id')
        if not campaign_affiliate_id:
            return Response(
                {'detail': 'campaign_affiliate_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            ca = CampaignAffiliate.objects.select_related(
                'campaign', 'affiliate'
            ).get(id=campaign_affiliate_id, removed_at__isnull=True)
        except CampaignAffiliate.DoesNotExist:
            return Response({'detail': 'Assignment not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Check if link already exists
        if AffiliateLink.objects.filter(campaign_affiliate=ca).exists():
            return Response({'detail': 'Link already generated for this assignment.'}, status=status.HTTP_400_BAD_REQUEST)

        slug     = attribution.generate_slug()
        from accounts.models import SystemSettings as _SS
        _base = _SS.get().tracking_base_url or getattr(settings, 'TRACKING_BASE_URL', 'https://leyyow.com')
        full_url = f"{_base.rstrip('/')}/r/{slug}/"
        code     = attribution.generate_code(ca.affiliate)

        with transaction.atomic():
            link = AffiliateLink.objects.create(
                campaign_affiliate = ca,
                campaign           = ca.campaign,
                affiliate          = ca.affiliate,
                slug               = slug,
                full_url           = full_url,
            )
            affiliate_code = AffiliateCode.objects.create(
                campaign_affiliate = ca,
                campaign           = ca.campaign,
                affiliate          = ca.affiliate,
                code               = code,
                is_custom          = False,
            )

        return Response({
            'link': AffiliateLinkSerializer(link).data,
            'code': AffiliateCodeSerializer(affiliate_code).data,
        }, status=status.HTTP_201_CREATED)


class UpdateAffiliateCodeView(APIView):
    """
    Affiliate updates their own coupon code.
    PATCH /api/affiliate/codes/<code_id>/
    """
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def patch(self, request, code_id):
        try:
            affiliate_code = AffiliateCode.objects.get(
                id=code_id,
                affiliate=request.user
            )
        except AffiliateCode.DoesNotExist:
            return Response({'detail': 'Code not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateAffiliateCodeSerializer(
            data=request.data,
            context={'code_id': code_id}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        old_code = affiliate_code.code
        affiliate_code.code      = serializer.validated_data['code']
        affiliate_code.is_custom = True
        affiliate_code.save(update_fields=['code', 'is_custom', 'updated_at'])

        log_action(
            actor_type='affiliate', actor_id=request.user.id,
            action='coupon_code.updated', entity_type='affiliate_code',
            entity_id=affiliate_code.id,
            changes={'before': {'code': old_code}, 'after': {'code': affiliate_code.code}},
        )

        return Response(AffiliateCodeSerializer(affiliate_code).data)


class RecordConversionView(APIView):
    """
    Internal endpoint called by the Leyyow subscription system when a
    merchant successfully subscribes and payment is confirmed (Decision 3).
    POST /api/internal/conversions/
    Secured by a shared secret header rather than JWT.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # Validate internal secret
        secret = request.headers.get('X-Internal-Secret', '')
        if secret != getattr(settings, 'INTERNAL_API_SECRET', ''):
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = RecordConversionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data                     = serializer.validated_data
        merchant_subscription_id = data['merchant_subscription_id']
        merchant_id              = data['merchant_id']
        merchant_name            = data.get('merchant_name')
        payment_amount           = data['payment_amount']
        external_payment_id      = data.get('external_payment_id')
        coupon_code              = data.get('coupon_code', '').strip()
        session_fingerprint      = data.get('session_fingerprint', '').strip()

        # Check for duplicate conversion
        if Conversion.objects.filter(
            merchant_subscription_id=merchant_subscription_id
        ).exists():
            return Response(
                {'detail': 'Conversion already recorded for this subscription.'},
                status=status.HTTP_409_CONFLICT
            )

        # Resolve attribution
        result = attribution.resolve_attribution(
            merchant_subscription_id = merchant_subscription_id,
            coupon_code              = coupon_code or None,
            session_fingerprint      = session_fingerprint or None,
        )

        if result['source'] == 'unattributed':
            return Response({'detail': 'Conversion recorded as unattributed. No commission issued.'})

        affiliate = result['affiliate']
        campaign  = result['campaign']

        # Self-referral check
        is_self_referral = str(affiliate.id) == str(merchant_id)
        if is_self_referral:
            return Response({'detail': 'Self-referral detected. No commission issued.'})

        with transaction.atomic():
            conversion = Conversion.objects.create(
                campaign                 = campaign,
                affiliate                = affiliate,
                attribution_source       = result['source'],
                affiliate_link           = result['link'],
                affiliate_code           = result['code'],
                merchant_subscription_id = merchant_subscription_id,
                merchant_id              = merchant_id,
                merchant_name            = merchant_name,
                registration_at          = now(),
                is_self_referral         = False,
            )

            # Update code use count if attributed via code
            if result['code']:
                result['code'].use_count += 1
                result['code'].save(update_fields=['use_count'])

            # Link click to conversion if attributed via link
            if result['link']:
                from tracking.models import LinkClick
                click = LinkClick.objects.filter(
                    affiliate_link      = result['link'],
                    is_duplicate        = False,
                    conversion__isnull  = True,
                ).order_by('-clicked_at').first()
                if click:
                    click.conversion = conversion
                    click.save(update_fields=['conversion'])

            # Create commission and credit wallets
            earned_commission = commission_engine.create_commission(
                conversion          = conversion,
                payment_amount_kobo = payment_amount,
                external_payment_id = external_payment_id,
            )

        return Response({
            'conversion': ConversionSerializer(conversion).data,
            'commission': CommissionSerializer(earned_commission).data,
        }, status=status.HTTP_201_CREATED)


class ReverseCommissionView(APIView):
    """
    Internal endpoint called when a merchant receives a refund (Decision 4).
    POST /api/internal/commissions/<commission_id>/reverse/
    """
    permission_classes = [AllowAny]

    def post(self, request, commission_id):
        secret = request.headers.get('X-Internal-Secret', '')
        if secret != getattr(settings, 'INTERNAL_API_SECRET', ''):
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            comm = Commission.objects.get(id=commission_id)
        except Commission.DoesNotExist:
            return Response({'detail': 'Commission not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            commission_engine.reverse_commission(comm)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'detail': 'Commission reversed successfully.'})


class AdminConversionListView(APIView):
    """List all conversions — admin side."""
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        conversions = Conversion.objects.select_related(
            'affiliate', 'campaign'
        ).order_by('-created_at')

        campaign_id = request.query_params.get('campaign_id')
        if campaign_id:
            conversions = conversions.filter(campaign_id=campaign_id)

        affiliate_id = request.query_params.get('affiliate_id')
        if affiliate_id:
            conversions = conversions.filter(affiliate_id=affiliate_id)

        serializer = ConversionSerializer(conversions, many=True)
        return Response({'count': conversions.count(), 'results': serializer.data})


class AdminCommissionListView(APIView):
    """List all commissions — admin side."""
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        commissions = Commission.objects.select_related(
            'affiliate', 'campaign', 'conversion'
        ).order_by('-earned_at')

        affiliate_id = request.query_params.get('affiliate_id')
        if affiliate_id:
            commissions = commissions.filter(affiliate_id=affiliate_id)

        campaign_id = request.query_params.get('campaign_id')
        if campaign_id:
            commissions = commissions.filter(campaign_id=campaign_id)

        comm_status = request.query_params.get('status')
        if comm_status:
            commissions = commissions.filter(status=comm_status)

        serializer = CommissionSerializer(commissions, many=True)
        return Response({'count': commissions.count(), 'results': serializer.data})

class MerchantLeadListView(APIView):
    """List merchant leads — admin side."""
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        from django.db.models import Count
        leads = MerchantLead.objects.select_related(
            'affiliate', 'campaign', 'affiliate_code'
        ).annotate(
            subscription_count=Count('conversions')
        ).order_by('-signed_up_at')

        campaign_id = request.query_params.get('campaign')
        if campaign_id:
            leads = leads.filter(campaign_id=campaign_id)

        affiliate_id = request.query_params.get('affiliate')
        if affiliate_id:
            leads = leads.filter(affiliate_id=affiliate_id)

        status_filter = request.query_params.get('status')
        if status_filter:
            leads = leads.filter(status=status_filter)

        data = [
            {
                'id':                 str(lead.id),
                'merchant_id':        lead.merchant_id,
                'merchant_name':      lead.merchant_name,
                'affiliate_name':     lead.affiliate.full_name,
                'campaign_name':      lead.campaign.name,
                'attribution_source': 'affiliate_code' if lead.affiliate_code_id else 'tracking_link',
                'signed_up_at':       lead.signed_up_at,
                'subscription_start': lead.subscription_start,
                'subscription_end':   lead.subscription_end,
                'subscription_tier':  lead.subscription_tier,
                'status':             lead.status,
                'subscription_count': lead.subscription_count,
            }
            for lead in leads
        ]

        return Response({'count': leads.count(), 'results': data})


class MerchantLeadDetailView(APIView):
    """Single merchant lead detail — admin side."""
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request, merchant_id):
        try:
            lead = MerchantLead.objects.select_related(
                'affiliate', 'campaign', 'affiliate_code'
            ).get(merchant_id=merchant_id)
        except MerchantLead.DoesNotExist:
            return Response({'detail': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)

        commissions = Commission.objects.filter(
            affiliate=lead.affiliate, conversion__lead=lead
        ).select_related('conversion').order_by('-earned_at')

        commission_rows = [
            {
                'id':            str(c.id),
                'amount':        c.amount,
                'status':        c.status,
                'earned_at':     c.earned_at,
                'event_type':    c.conversion.merchant_subscription_id,
            }
            for c in commissions
        ]

        return Response({
            'id':                      str(lead.id),
            'merchant_id':             lead.merchant_id,
            'merchant_name':           lead.merchant_name,
            'status':                  lead.status,
            'affiliate_id':            str(lead.affiliate.id),
            'affiliate_name':          lead.affiliate.full_name,
            'campaign_id':             str(lead.campaign.id),
            'campaign_name':           lead.campaign.name,
            'affiliate_code':          lead.affiliate_code.code if lead.affiliate_code else None,
            'subscription_tier':       lead.subscription_tier,
            'subscription_start':      lead.subscription_start,
            'subscription_end':        lead.subscription_end,
            'amount_paid_kobo':        lead.amount_paid_kobo,
            'total_amount_paid_kobo':  lead.total_amount_paid_kobo,
            'first_subscribed_at':     lead.first_subscribed_at,
            'first_subscription_tier': lead.first_subscription_tier,
            'signed_up_at':            lead.signed_up_at,
            'updated_at':              lead.updated_at,
            'commissions':             commission_rows,
        })