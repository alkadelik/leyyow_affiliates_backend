from django.utils.timezone import now
from django.core.exceptions import ValidationError
from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework_simplejwt.authentication import JWTAuthentication

from campaigns.models import Campaign, CampaignAffiliate
from campaigns.serializers import (
    CampaignListSerializer,
    CampaignDetailSerializer,
    CreateCampaignSerializer,
    UpdateCampaignSerializer,
    TransitionCampaignSerializer,
    AssignAffiliateSerializer,
    RemoveAffiliateSerializer,
)
from campaigns import state_machine
from accounts.models import Affiliate, SystemSettings
from accounts.permissions import IsAnyAdmin
from audit.utils import log_action
from campaigns.task import (
    task_send_campaign_invite,
    task_send_campaign_going_live, #send_campaign_live_email?
    task_send_campaign_ended,
)
from tracking.models import AffiliateLink, AffiliateCode
import uuid, secrets, string
from django.conf import settings


def _generate_code(affiliate):
    """Generate a unique affiliate code in FIRSTNAME-XXXX format."""
    first_name = affiliate.full_name.split()[0].upper()
    while True:
        suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        code = f"{first_name}-{suffix}"
        if not AffiliateCode.objects.filter(code=code).exists():
            return code


def _generate_slug():
    """Generate a unique URL slug."""
    while True:
        slug = secrets.token_urlsafe(8)
        if not AffiliateLink.objects.filter(slug=slug).exists():
            return slug


class CampaignListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        campaigns = Campaign.objects.select_related('created_by').order_by('-created_at')

        # Filter by status
        status_filter = request.query_params.get('status')
        if status_filter:
            campaigns = campaigns.filter(status=status_filter)

        # Search by name
        search = request.query_params.get('search')
        if search:
            campaigns = campaigns.filter(name__icontains=search)

        serializer = CampaignListSerializer(campaigns, many=True)
        return Response({
            'count':   campaigns.count(),
            'results': serializer.data,
        })

    def post(self, request):
        is_draft = request.data.get('is_draft', False)
        serializer = CreateCampaignSerializer(data=request.data, context={'is_draft': is_draft})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data     = serializer.validated_data
        campaign = Campaign.objects.create(
            name                 = data['name'],
            description          = data.get('description'),
            commission_type      = data['commission_type'],
            commission_value     = data['commission_value'],
            commission_cap       = data.get('commission_cap'),
            tier                 = data.get('tier'),
            starts_at            = data.get('starts_at'),
            ends_at              = data.get('ends_at'),
            conversion_limit     = data.get('conversion_limit'),
            terms_and_conditions = data.get('terms_and_conditions'),
            commission_trigger      = data.get('commission_trigger'),
            commission_period_days  = data.get('commission_period_days'),
            commission_per_tier     = data.get('commission_per_tier'),
            status               = 'draft',
            created_by           = request.user,
        )

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action='campaign.created', entity_type='campaign',
            entity_id=campaign.id,
        )

        return Response(
            CampaignDetailSerializer(campaign).data,
            status=status.HTTP_201_CREATED
        )


class CampaignDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get_campaign(self, campaign_id):
        try:
            return Campaign.objects.select_related('created_by').get(id=campaign_id)
        except Campaign.DoesNotExist:
            return None

    def get(self, request, campaign_id):
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return Response({'detail': 'Campaign not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CampaignDetailSerializer(campaign).data)

    def patch(self, request, campaign_id):
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return Response({'detail': 'Campaign not found.'}, status=status.HTTP_404_NOT_FOUND)

        if campaign.status not in ('draft', 'scheduled'):
            return Response(
                {'detail': 'Campaign can only be edited while in draft or scheduled status.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        is_draft = request.data.get('is_draft', True)
        serializer = UpdateCampaignSerializer(data=request.data, partial=True, context={'is_draft': is_draft})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        for field, value in data.items():
            setattr(campaign, field, value)
        campaign.save()

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action='campaign.updated', entity_type='campaign',
            entity_id=campaign.id,
        )

        return Response(CampaignDetailSerializer(campaign).data)


class CampaignTransitionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    ACTION_TO_STATUS = {
        'schedule': 'scheduled',
        'start':    'active',
        'end':      'ended',
        'cancel':   'cancelled',
    }

    def post(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({'detail': 'Campaign not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TransitionCampaignSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data['action']

        # ADD: auto-resolve start → scheduled if start date is in the future
        if action == 'start':
            if campaign.starts_at and campaign.starts_at.date() > now().date():
                target_status = 'scheduled'
            else:
                target_status = 'active'
        else:
            target_status = self.ACTION_TO_STATUS[action]

        try:
            state_machine.transition(campaign, target_status, performed_by=request.user)
        except ValidationError as e:
            return Response({'detail': str(e.message)}, status=status.HTTP_400_BAD_REQUEST)

        campaign.save()

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action=f'campaign.{action}d', entity_type='campaign',
            entity_id=campaign.id,
        )

        if target_status == 'active':
            task_send_campaign_going_live.delay(str(campaign.id))
            assigned = CampaignAffiliate.objects.filter(
                campaign=campaign, removed_at__isnull=True
            ).select_related('affiliate')
            for ca in assigned:
                ca.affiliate.status = 'active'
                ca.affiliate.save(update_fields=['status'])
                task_send_campaign_invite.delay(str(ca.affiliate.id), campaign)

        if target_status in ('ended', 'cancelled'):
            if target_status == 'ended':
                task_send_campaign_ended.delay(str(campaign))
            assigned = CampaignAffiliate.objects.filter(
                campaign=campaign, removed_at__isnull=True
            ).select_related('affiliate')
            for ca in assigned:
                still_active = CampaignAffiliate.objects.filter(
                    affiliate=ca.affiliate,
                    removed_at__isnull=True,
                    campaign__status='active'
                ).exclude(campaign=campaign).exists()
                ca.affiliate.status = 'active' if still_active else 'inactive'
                ca.affiliate.save(update_fields=['status'])

        return Response(CampaignDetailSerializer(campaign).data)


class CampaignAffiliateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def post(self, request, campaign_id):
        """Assign an affiliate to a campaign."""
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({'detail': 'Campaign not found.'}, status=status.HTTP_404_NOT_FOUND)

        if campaign.status == 'cancelled':
            return Response(
                {'detail': 'Cannot assign affiliates to a cancelled campaign.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if campaign.status == 'ended':
            return Response(
                {'detail': 'Cannot assign affiliates to an ended campaign.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = AssignAffiliateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        affiliate_id = serializer.validated_data['affiliate_id']
        affiliate    = Affiliate.objects.get(id=affiliate_id)

        # Check if already assigned and active
        existing = CampaignAffiliate.objects.filter(
            campaign=campaign,
            affiliate=affiliate,
            removed_at__isnull=True
        ).first()

        if existing:
            return Response(
                {'detail': 'Affiliate is already assigned to this campaign.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if previously removed — reinstate instead of creating new
        previously_removed = CampaignAffiliate.objects.filter(
            campaign=campaign,
            affiliate=affiliate,
            removed_at__isnull=False
        ).first()

        if previously_removed:
            previously_removed.removed_at = None
            previously_removed.removed_by = None
            previously_removed.assigned_by = request.user
            previously_removed.save(update_fields=['removed_at', 'removed_by', 'assigned_by'])
            ca = previously_removed
        else:
            ca = CampaignAffiliate.objects.create(
                campaign = campaign,
                affiliate = affiliate,
                assigned_by = request.user,
            )

        # Generate affiliate code if it doesn't exist
        if not AffiliateCode.objects.filter(campaign_affiliate=ca).exists():
            AffiliateCode.objects.create(
                campaign_affiliate = ca,
                campaign = campaign,
                affiliate = affiliate,
                code = _generate_code(affiliate),
            )

        # Generate affiliate link if it doesn't exist
        if not AffiliateLink.objects.filter(campaign_affiliate=ca).exists():
            slug = _generate_slug()
            AffiliateLink.objects.create(
                campaign_affiliate = ca,
                campaign = campaign,
                affiliate = affiliate,
                slug = slug,
                full_url = f"{(SystemSettings.get().tracking_base_url or getattr(settings, 'TRACKING_BASE_URL', 'https://leyyow.com')).rstrip('/')}/r/{slug}",
            )

        if campaign.status in ('active', 'scheduled'):
            affiliate.status = 'active'
            affiliate.save(update_fields=['status'])
            task_send_campaign_invite.delay(str(affiliate.id), campaign)

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action='campaign.affiliate_assigned', entity_type='campaign',
            entity_id=campaign.id,
            metadata={'affiliate_id': str(affiliate_id)},
        )

        return Response(
            CampaignDetailSerializer(campaign).data,
            status=status.HTTP_201_CREATED
        )

    def delete(self, request, campaign_id):
        """Remove an affiliate from a campaign."""
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({'detail': 'Campaign not found.'}, status=status.HTTP_404_NOT_FOUND)

        if campaign.status not in ('draft', 'scheduled', 'active'):
            return Response(
                {'detail': 'Affiliates can only be removed from draft or scheduled campaigns.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = RemoveAffiliateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        affiliate_id = serializer.validated_data['affiliate_id']
        affiliate = Affiliate.objects.get(id=affiliate_id)

        assignment = CampaignAffiliate.objects.filter(
            campaign_id  = campaign_id,
            affiliate_id = affiliate_id,
            removed_at__isnull = True,
        ).first()

        if not assignment:
            return Response(
                {'detail': 'Affiliate is not assigned to this campaign.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        assignment.removed_at = now()
        assignment.removed_by = request.user
        assignment.save(update_fields=['removed_at', 'removed_by'])

        still_active = CampaignAffiliate.objects.filter(
            affiliate=affiliate,
            removed_at__isnull=True,
            campaign__status='active'
        ).exists()
        affiliate.status = 'active' if still_active else 'inactive'
        affiliate.save(update_fields=['status'])

        log_action(
            actor_type='admin', actor_id=request.user.id,
            action='campaign.affiliate_removed', entity_type='campaign',
            entity_id=campaign.id,
            metadata={'affiliate_id': str(affiliate_id)},
        )

        return Response({'detail': 'Affiliate removed from campaign.'})