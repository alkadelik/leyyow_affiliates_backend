import hashlib
import hmac
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import timedelta

from .models import AffiliateCode, MerchantLead, Conversion, Commission, CentralWallet
from accounts.models import AffiliateWallet
from audit.utils import log_action
from tracking.commission import _check_eligibility


def verify_internal_key(request):
    key = request.headers.get('X-Internal-API-Key', '')
    return hmac.compare_digest(key, settings.LEYYOW_INTERNAL_SECRET_KEY)


class MerchantSignupView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if not verify_internal_key(request):
            return Response({'error': 'Unauthorised'}, status=status.HTTP_401_UNAUTHORIZED)

        merchant_id   = request.data.get('merchant_id')
        merchant_name = request.data.get('merchant_name')
        code_str      = request.data.get('affiliate_code')
        signed_up_at  = request.data.get('signed_up_at', timezone.now())

        if not all([merchant_id, merchant_name, code_str]):
            return Response({'error': 'merchant_id, merchant_name and affiliate_code are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            affiliate_code = AffiliateCode.objects.select_related(
                'affiliate', 'campaign'
            ).get(code=code_str)
        except AffiliateCode.DoesNotExist:
            return Response({'error': 'Invalid affiliate code'}, status=status.HTTP_404_NOT_FOUND)

        campaign = affiliate_code.campaign
        if campaign.status != 'active':
            return Response({'error': 'Campaign is not active'}, status=status.HTTP_400_BAD_REQUEST)

        if MerchantLead.objects.filter(merchant_id=merchant_id).exists():
            return Response({'error': 'Merchant already recorded'}, status=status.HTTP_409_CONFLICT)

        lead = MerchantLead.objects.create(
            affiliate_code=affiliate_code,
            affiliate=affiliate_code.affiliate,
            campaign=campaign,
            merchant_id=merchant_id,
            merchant_name=merchant_name,
            status='trial',
            signed_up_at=signed_up_at,
        )

        log_action(
            actor_type='system',
            action='merchant_signup',
            entity_type='merchant_lead',
            entity_id=str(lead.id),
            metadata={'merchant_id': merchant_id, 'affiliate_code': code_str}
        )

        return Response({'lead_id': str(lead.id)}, status=status.HTTP_201_CREATED)
    

class MerchantSubscriptionView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        if not verify_internal_key(request):
            return Response({'error': 'Unauthorised'}, status=status.HTTP_401_UNAUTHORIZED)

        merchant_id           = request.data.get('merchant_id')
        event_type            = request.data.get('event_type')
        subscription_tier     = request.data.get('subscription_tier')
        subscription_start    = request.data.get('subscription_start')
        subscription_end      = request.data.get('subscription_end')
        amount_paid_kobo      = request.data.get('amount_paid_kobo')
        merchant_subscription_id = request.data.get('merchant_subscription_id')
        occurred_at           = request.data.get('occurred_at', timezone.now())

        if not all([merchant_id, event_type, occurred_at]):
            return Response({'error': 'merchant_id, event_type and occurred_at are required'},
                            status=status.HTTP_400_BAD_REQUEST)

        if event_type not in ('subscribed', 'renewed', 'expired', 'cancelled', 'trial_ended'):
            return Response({'error': 'Invalid event_type'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lead = MerchantLead.objects.select_related(
                'affiliate', 'campaign', 'affiliate_code'
            ).get(merchant_id=merchant_id)
        except MerchantLead.DoesNotExist:
            return Response({'error': 'Merchant lead not found'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            # Update lead
            lead.status           = _map_event_to_status(event_type)
            lead.subscription_tier  = subscription_tier or lead.subscription_tier
            lead.subscription_start = subscription_start or lead.subscription_start
            lead.subscription_end   = subscription_end or lead.subscription_end
            lead.amount_paid_kobo   = amount_paid_kobo or lead.amount_paid_kobo

            if event_type in ('subscribed', 'renewed') and amount_paid_kobo:
                lead.total_amount_paid_kobo += amount_paid_kobo

            if event_type in ('subscribed', 'renewed') and lead.first_subscribed_at is None:
                lead.first_subscribed_at     = occurred_at
                lead.first_subscription_tier = subscription_tier

            lead.save()

            commission_created = False

            if event_type in ('subscribed', 'renewed'):
                eligible, amount = _check_eligibility(lead, occurred_at, amount_paid_kobo)

                if eligible:
                    conversion = Conversion.objects.create(
                        campaign=lead.campaign,
                        affiliate=lead.affiliate,
                        attribution_source='coupon_code',
                        affiliate_code=lead.affiliate_code,
                        merchant_subscription_id=merchant_subscription_id or '',
                        merchant_id=lead.merchant_id,
                        merchant_name=lead.merchant_name,
                        registration_at=lead.signed_up_at,
                        converted_at=occurred_at,
                        lead=lead,
                    )

                    campaign = lead.campaign
                    commission = Commission.objects.create(
                        conversion=conversion,
                        affiliate=lead.affiliate,
                        campaign=campaign,
                        status='earned',
                        amount=amount,
                        payment_amount=amount,
                        commission_type_snapshot=campaign.commission_type,
                        commission_value_snapshot=campaign.commission_value,
                        commission_cap_snapshot=campaign.commission_cap,
                        earned_at=occurred_at,
                    )

                    # Credit affiliate wallet
                    wallet, _ = AffiliateWallet.objects.get_or_create(affiliate=lead.affiliate)
                    wallet.balance        += amount
                    wallet.total_earned   += amount
                    wallet.save()

                    # Debit central wallet
                    central = CentralWallet.objects.select_for_update().get(id=1)
                    central.balance                     -= amount
                    central.total_commissions_allocated += amount
                    central.save()

                    commission_created = True

                    log_action(
                        actor_type='system',
                        action='commission_earned',
                        entity_type='commission',
                        entity_id=str(commission.id),
                        metadata={
                            'merchant_id': merchant_id,
                            'event_type': event_type,
                            'amount': amount,
                        }
                    )

            log_action(
                actor_type='system',
                action=f'merchant_{event_type}',
                entity_type='merchant_lead',
                entity_id=str(lead.id),
                metadata={
                    'merchant_id': merchant_id,
                    'event_type': event_type,
                    'commission_created': commission_created,
                }
            )

        return Response({
            'lead_id': str(lead.id),
            'commission_created': commission_created,
        }, status=status.HTTP_200_OK)


class MerchantLeadInternalListView(APIView):
    authentication_classes = []
    permission_classes     = []

    def get(self, request):
        if not verify_internal_key(request):
            return Response({'error': 'Unauthorised'}, status=status.HTTP_401_UNAUTHORIZED)

        leads = MerchantLead.objects.select_related(
            'affiliate', 'campaign', 'affiliate_code'
        ).order_by('-signed_up_at')

        data = [
            {
                'id':                 str(lead.id),
                'merchant_id':        lead.merchant_id,
                'merchant_name':      lead.merchant_name,
                'affiliate_name':     lead.affiliate.full_name,
                'campaign_name':      lead.campaign.name,
                'signed_up_at':       lead.signed_up_at,
                'subscription_start': lead.subscription_start,
                'subscription_end':   lead.subscription_end,
                'subscription_tier':  lead.subscription_tier,
                'status':             lead.status,
            }
            for lead in leads
        ]

        return Response({'count': len(data), 'results': data})


def _map_event_to_status(event_type):
    return {
        'subscribed':   'subscribed',
        'renewed':      'subscribed',
        'expired':      'expired',
        'cancelled':    'cancelled',
        'trial_ended':  'signed_up',
    }[event_type]