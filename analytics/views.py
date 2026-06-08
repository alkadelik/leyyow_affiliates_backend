from django.db import models as db_models
from django.utils.timezone import now, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import Affiliate, AffiliateWallet
from accounts.permissions import IsAnyAdmin, IsAffiliate
from accounts.backends import AffiliateJWTAuthentication
from campaigns.models import Campaign, CampaignAffiliate
from tracking.models import (
    AffiliateLink, AffiliateCode, LinkClick,
    Conversion, Commission, CentralWallet, MerchantLead
)
from payouts.models import PayoutRequest


# ── Admin analytics views ─────────────────────────────────────────────────────

class AdminOverviewAnalyticsView(APIView):
    """
    Step 56 — Leyyow admin analytics.
    Overall ROI, campaign performance, affiliate rankings, conversion rates.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        # Date range filter — default last 30 days
        days  = int(request.query_params.get('days', 30))
        since = now() - timedelta(days=days)

        # ── Overall stats ────────────────────────────────────────────────────
        total_affiliates  = Affiliate.objects.filter(status='active').count()
        total_campaigns   = Campaign.objects.count()
        active_campaigns  = Campaign.objects.filter(status='active').count()

        total_conversions = Conversion.objects.filter(
            created_at__gte=since
        ).count()

        total_clicks = LinkClick.objects.filter(
            clicked_at__gte=since,
            is_duplicate=False,
        ).count()

        total_commissions = Commission.objects.filter(
            earned_at__gte=since,
            status='earned',
        ).aggregate(
            total=db_models.Sum('amount')
        )['total'] or 0

        total_leads      = MerchantLead.objects.filter(signed_up_at__gte=since).count()
        total_subscribed = MerchantLead.objects.filter(signed_up_at__gte=since, status='subscribed').count()
        conversion_rate = (
            round(total_subscribed / total_leads * 100, 2)
            if total_leads > 0 else 0
        )

        # ── Campaign performance ─────────────────────────────────────────────
        campaigns = Campaign.objects.annotate(
            conversion_count=db_models.Count(
                'conversions',
                filter=db_models.Q(conversions__created_at__gte=since)
            ),
            commission_total=db_models.Sum(
                'commissions__amount',
                filter=db_models.Q(
                    commissions__earned_at__gte=since,
                    commissions__status='earned',
                )
            ),
            click_count=db_models.Count(
                'clicks',
                filter=db_models.Q(
                    clicks__clicked_at__gte=since,
                    clicks__is_duplicate=False,
                )
            ),
        ).order_by('-conversion_count')[:10]

        campaign_performance = [
            {
                'id':               str(c.id),
                'name':             c.name,
                'status':           c.status,
                'conversion_count': c.conversion_count,
                'commission_total': c.commission_total or 0,
                'click_count':      c.click_count,
                'conversion_rate':  round(
                    c.conversion_count / c.click_count * 100, 2
                ) if c.click_count > 0 else 0,
            }
            for c in campaigns
        ]

        # ── Affiliate rankings ───────────────────────────────────────────────
        affiliate_rankings = Commission.objects.filter(
            earned_at__gte=since,
            status='earned',
        ).values(
            'affiliate__id',
            'affiliate__full_name',
            'affiliate__email',
        ).annotate(
            total_earned=db_models.Sum('amount'),
            conversion_count=db_models.Count('conversion', distinct=True),
        ).order_by('-total_earned')[:10]

        rankings = [
            {
                'affiliate_id':    str(r['affiliate__id']),
                'full_name':       r['affiliate__full_name'],
                'email':           r['affiliate__email'],
                'total_earned':    r['total_earned'],
                'conversion_count': r['conversion_count'],
            }
            for r in affiliate_rankings
        ]

        # ── Monthly trend — last 6 months ────────────────────────────────────
        monthly_trend = []
        for i in range(5, -1, -1):
            month_start = (now().replace(day=1) - timedelta(days=i * 30)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            month_end = (month_start + timedelta(days=31)).replace(day=1)

            month_commissions = Commission.objects.filter(
                earned_at__gte=month_start,
                earned_at__lt=month_end,
                status='earned',
            ).aggregate(total=db_models.Sum('amount'))['total'] or 0

            month_conversions = Conversion.objects.filter(
                created_at__gte=month_start,
                created_at__lt=month_end,
            ).count()

            monthly_trend.append({
                'month':       month_start.strftime('%b %Y'),
                'commissions': month_commissions,
                'conversions': month_conversions,
            })

        return Response({
            'period_days':        days,
            'overview': {
                'total_affiliates':  total_affiliates,
                'total_campaigns':   total_campaigns,
                'active_campaigns':  active_campaigns,
                'total_conversions': total_conversions,
                'total_clicks':      total_clicks,
                'total_commissions': total_commissions,
                'conversion_rate':   conversion_rate,
            },
            'campaign_performance': campaign_performance,
            'affiliate_rankings':   rankings,
            'monthly_trend':        monthly_trend,
        })


class AdminCampaignAnalyticsView(APIView):
    """Detailed analytics for a single campaign."""
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({'detail': 'Campaign not found.'}, status=status.HTTP_404_NOT_FOUND)

        from tracking.models import MerchantLead

        # Overall campaign stats
        total_clicks = LinkClick.objects.filter(
            campaign=campaign, is_duplicate=False
        ).count()

        total_leads = MerchantLead.objects.filter(campaign=campaign).count()

        total_subscribed = MerchantLead.objects.filter(
            campaign=campaign, status='subscribed'
        ).count()

        total_sales = MerchantLead.objects.filter(
            campaign=campaign, status='subscribed'
        ).aggregate(total=db_models.Sum('amount_paid_kobo'))['total'] or 0

        total_commissions = Commission.objects.filter(
            campaign=campaign, status='earned'
        ).aggregate(total=db_models.Sum('amount'))['total'] or 0

        conversion_rate = (
            round(total_subscribed / total_leads * 100, 2)
            if total_leads > 0 else None
        )

        roi = (
            round((total_commissions / total_sales) * 100, 2)
            if total_sales > 0 else None
        )

        # Per-affiliate breakdown
        assignments = CampaignAffiliate.objects.filter(
            campaign=campaign,
            removed_at__isnull=True,
        ).select_related('affiliate')

        affiliate_breakdown = []
        for ca in assignments:
            aff = ca.affiliate

            aff_clicks = LinkClick.objects.filter(
                campaign=campaign, affiliate=aff, is_duplicate=False
            ).count()

            aff_leads = MerchantLead.objects.filter(
                campaign=campaign, affiliate=aff
            ).count()

            aff_conversions = MerchantLead.objects.filter(
                campaign=campaign, affiliate=aff, status='subscribed'
            ).count()

            aff_sales = MerchantLead.objects.filter(
                campaign=campaign, affiliate=aff, status='subscribed'
            ).aggregate(total=db_models.Sum('amount_paid_kobo'))['total'] or 0

            aff_earned = Commission.objects.filter(
                campaign=campaign, affiliate=aff, status='earned'
            ).aggregate(total=db_models.Sum('amount'))['total'] or 0

            aff_conversion_rate = (
                round(aff_conversions / aff_leads * 100, 2)
                if aff_leads > 0 else None
            )

            aff_roi = (
                round((aff_earned / aff_sales) * 100, 2)
                if aff_sales > 0 else None
            )

            try:
                link_url = ca.link.full_url
            except Exception:
                link_url = None

            try:
                code_str = ca.code.code
            except Exception:
                code_str = None

            affiliate_breakdown.append({
                'affiliate_id':    str(aff.id),
                'full_name':       aff.full_name,
                'email':           aff.email,
                'link_url':        link_url,
                'affiliate_code':  code_str,
                'click_count':     aff_clicks,
                'conversion_count': aff_conversions,
                'total_earned':    aff_earned,
                'roi':             aff_roi,
                'conversion_rate': aff_conversion_rate,
            })

        return Response({
            'campaign': {
                'id':     str(campaign.id),
                'name':   campaign.name,
                'status': campaign.status,
            },
            'overview': {
                'total_clicks':      total_clicks,
                'total_conversions': total_subscribed,
                'total_commissions': total_commissions,
                'total_sales':       total_sales,
                'conversion_rate':   conversion_rate,
                'roi':               roi,
            },
            'affiliate_breakdown': affiliate_breakdown,
        })


# ── Affiliate analytics views ─────────────────────────────────────────────────

class AffiliateEarningsAnalyticsView(APIView):
    """
    Step 57 — Affiliate earnings history and stats.
    Per-campaign breakdown: clicks, conversions, earnings, ROI.
    """
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        affiliate = request.user

        # Date range — default all time
        days  = request.query_params.get('days')
        since = now() - timedelta(days=int(days)) if days else None

        # Overall totals
        commission_qs = Commission.objects.filter(affiliate=affiliate)
        if since:
            commission_qs = commission_qs.filter(earned_at__gte=since)

        total_earned = commission_qs.filter(
            status='earned'
        ).aggregate(
            total=db_models.Sum('amount')
        )['total'] or 0

        total_reversed = commission_qs.filter(
            status='reversed'
        ).aggregate(
            total=db_models.Sum('amount')
        )['total'] or 0

        click_qs = LinkClick.objects.filter(affiliate=affiliate, is_duplicate=False)
        if since:
            click_qs = click_qs.filter(clicked_at__gte=since)
        total_clicks = click_qs.count()

        conversion_qs = Conversion.objects.filter(affiliate=affiliate)
        if since:
            conversion_qs = conversion_qs.filter(created_at__gte=since)
        total_conversions = conversion_qs.count()

        conversion_rate = (
            round(total_conversions / total_clicks * 100, 2)
            if total_clicks > 0 else 0
        )

        # Per-campaign breakdown
        assignments = CampaignAffiliate.objects.filter(
            affiliate=affiliate,
        ).select_related('campaign')

        campaign_breakdown = []
        for ca in assignments:
            campaign = ca.campaign

            camp_click_qs = LinkClick.objects.filter(
                affiliate=affiliate, campaign=campaign, is_duplicate=False
            )
            if since:
                camp_click_qs = camp_click_qs.filter(clicked_at__gte=since)
            camp_clicks = camp_click_qs.count()

            camp_conv_qs = Conversion.objects.filter(
                affiliate=affiliate, campaign=campaign
            )
            if since:
                camp_conv_qs = camp_conv_qs.filter(created_at__gte=since)
            camp_conversions = camp_conv_qs.count()

            camp_earned = Commission.objects.filter(
                affiliate=affiliate,
                campaign=campaign,
                status='earned',
            )
            if since:
                camp_earned = camp_earned.filter(earned_at__gte=since)
            camp_total = camp_earned.aggregate(
                total=db_models.Sum('amount')
            )['total'] or 0

            campaign_breakdown.append({
                'campaign_id':     str(campaign.id),
                'campaign_name':   campaign.name,
                'campaign_status': campaign.status,
                'clicks':          camp_clicks,
                'conversions':     camp_conversions,
                'total_earned':    camp_total,
                'conversion_rate': round(
                    camp_conversions / camp_clicks * 100, 2
                ) if camp_clicks > 0 else 0,
            })

        # Sort by total earned descending
        campaign_breakdown.sort(key=lambda x: x['total_earned'], reverse=True)

        # Monthly trend — last 6 months
        monthly_trend = []
        for i in range(5, -1, -1):
            month_start = (now().replace(day=1) - timedelta(days=i * 30)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            month_end = (month_start + timedelta(days=31)).replace(day=1)

            month_earned = Commission.objects.filter(
                affiliate=affiliate,
                earned_at__gte=month_start,
                earned_at__lt=month_end,
                status='earned',
            ).aggregate(total=db_models.Sum('amount'))['total'] or 0

            month_conversions = Conversion.objects.filter(
                affiliate=affiliate,
                created_at__gte=month_start,
                created_at__lt=month_end,
            ).count()

            monthly_trend.append({
                'month':       month_start.strftime('%b %Y'),
                'earned':      month_earned,
                'conversions': month_conversions,
            })

        # Wallet snapshot
        try:
            wallet = affiliate.wallet
            wallet_data = {
                'balance':        wallet.balance,
                'total_earned':   wallet.total_earned,
                'total_withdrawn': wallet.total_withdrawn,
            }
        except Exception:
            wallet_data = {
                'balance': 0, 'total_earned': 0, 'total_withdrawn': 0
            }

        return Response({
            'period_days': days or 'all',
            'overview': {
                'total_earned':      total_earned,
                'total_reversed':    total_reversed,
                'net_earned':        total_earned - total_reversed,
                'total_clicks':      total_clicks,
                'total_conversions': total_conversions,
                'conversion_rate':   conversion_rate,
            },
            'wallet':             wallet_data,
            'campaign_breakdown': campaign_breakdown,
            'monthly_trend':      monthly_trend,
        })
    
class AdminAffiliateAnalyticsView(APIView):
    """Detailed analytics for a single affiliate — admin side."""
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request, affiliate_id):
        try:
            affiliate = Affiliate.objects.get(id=affiliate_id)
        except Affiliate.DoesNotExist:
            return Response({'detail': 'Affiliate not found.'}, status=status.HTTP_404_NOT_FOUND)

        from tracking.models import MerchantLead

        total_earned = Commission.objects.filter(
            affiliate=affiliate, status='earned'
        ).aggregate(total=db_models.Sum('amount'))['total'] or 0

        total_leads = MerchantLead.objects.filter(affiliate=affiliate).count()

        total_conversions = MerchantLead.objects.filter(
            affiliate=affiliate, status='subscribed'
        ).count()

        total_sales = MerchantLead.objects.filter(
            affiliate=affiliate, status='subscribed'
        ).aggregate(total=db_models.Sum('amount_paid_kobo'))['total'] or 0

        conversion_rate = (
            round(total_conversions / total_leads * 100, 2)
            if total_leads > 0 else None
        )

        roi = (
            round((total_earned / total_sales) * 100, 2)
            if total_sales > 0 else None
        )

        assignments = CampaignAffiliate.objects.filter(
            affiliate=affiliate
        ).select_related('campaign')

        live_campaigns  = assignments.filter(campaign__status='active').count()
        ended_campaigns = assignments.filter(campaign__status='ended').count()
        total_campaigns = assignments.count()

        return Response({
            'total_earned':      total_earned,
            'total_sales':       total_sales,
            'conversion_rate':   f"{conversion_rate}%" if conversion_rate else None,
            'roi':               f"{roi}%" if roi else None,
            'total_campaigns':   total_campaigns,
            'live_campaigns':    live_campaigns,
            'ended_campaigns':   ended_campaigns,
            'total_conversions': total_conversions,
        })