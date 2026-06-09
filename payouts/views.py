from django.utils.timezone import now
from django.db import transaction
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from rest_framework_simplejwt.authentication import JWTAuthentication

from payouts.models import BankAccount, PayoutRequest
from payouts.serializers import (
    BankAccountSerializer,
    AddBankAccountSerializer,
    PayoutRequestSerializer,
    CreatePayoutRequestSerializer,
    AdminPayoutRequestSerializer,
    AdminPayoutActionSerializer,
)
from payouts.paystack import create_recipient, initiate_transfer
from payouts.task import task_send_payout_approved, task_send_payout_cancelled
from accounts.models import AffiliateWallet, SystemSettings
from accounts.permissions import IsAnyAdmin, IsAffiliate
from accounts.backends import AffiliateJWTAuthentication
from tracking.models import CentralWallet, Commission
from audit.utils import log_action
from django.db import models as db_models

import time

TRANSFER_FEE   = 10000   # ₦100 in kobo
MINIMUM_PAYOUT = 5000000  # ₦50,000 in kobo


# ── Affiliate bank account views ──────────────────────────────────────────────

class BankAccountListView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        accounts = BankAccount.objects.filter(
            affiliate  = request.user,
            deleted_at__isnull = True,
        )
        return Response(BankAccountSerializer(accounts, many=True).data)

    def post(self, request):
        serializer = AddBankAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data       = serializer.validated_data
        is_default = data.get('is_default', False)

        # Create Paystack recipient before saving to DB
        try:
            recipient_code = create_recipient(
                bank_name      = data['bank_name'],
                account_number = data['account_number'],
                account_name   = data['account_name'],
                bank_code      = data['bank_code'],
            )
        except ValueError as e:
            return Response(
                {'detail': f'Could not verify bank account with Paystack: {e}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # If this is default, unset all others
            if is_default:
                BankAccount.objects.filter(
                    affiliate  = request.user,
                    deleted_at__isnull = True,
                ).update(is_default=False)

            # If this is first account, make it default automatically
            existing_count = BankAccount.objects.filter(
                affiliate  = request.user,
                deleted_at__isnull = True,
            ).count()

            if existing_count == 0:
                is_default = True

            account = BankAccount.objects.create(
                affiliate               = request.user,
                bank_name               = data['bank_name'],
                bank_code               = data['bank_code'],
                account_number          = data['account_number'],
                account_name            = data['account_name'],
                is_default              = is_default,
                paystack_recipient_code = recipient_code,
            )

        log_action(
            actor_type='affiliate', actor_id=request.user.id,
            action='bank_account.added', entity_type='bank_account',
            entity_id=account.id,
        )

        return Response(BankAccountSerializer(account).data, status=status.HTTP_201_CREATED)


class BankAccountDetailView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def delete(self, request, account_id):
        try:
            account = BankAccount.objects.get(
                id         = account_id,
                affiliate  = request.user,
                deleted_at__isnull = True,
            )
        except BankAccount.DoesNotExist:
            return Response({'detail': 'Bank account not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Block deletion if there is a pending payout using this account
        if PayoutRequest.objects.filter(
            bank_account = account,
            status       = 'pending',
        ).exists():
            return Response(
                {'detail': 'Cannot delete a bank account with a pending payout request.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        account.deleted_at = now()
        account.save(update_fields=['deleted_at'])

        # If it was the default, assign default to another account if one exists
        if account.is_default:
            account.is_default = False
            account.save(update_fields=['is_default'])
            next_account = BankAccount.objects.filter(
                affiliate  = request.user,
                deleted_at__isnull = True,
            ).first()
            if next_account:
                next_account.is_default = True
                next_account.save(update_fields=['is_default'])

        log_action(
            actor_type='affiliate', actor_id=request.user.id,
            action='bank_account.deleted', entity_type='bank_account',
            entity_id=account.id,
        )

        return Response({'detail': 'Bank account removed.'})

    def patch(self, request, account_id):
        """Set an account as the default."""
        try:
            account = BankAccount.objects.get(
                id         = account_id,
                affiliate  = request.user,
                deleted_at__isnull = True,
            )
        except BankAccount.DoesNotExist:
            return Response({'detail': 'Bank account not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            BankAccount.objects.filter(
                affiliate  = request.user,
                deleted_at__isnull = True,
            ).update(is_default=False)
            account.is_default = True
            account.save(update_fields=['is_default'])

        return Response(BankAccountSerializer(account).data)


# ── Affiliate wallet view ─────────────────────────────────────────────────────

class AffiliateWalletView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        try:
            wallet = request.user.wallet
        except Exception:
            return Response({
                'balance':         0,
                'total_earned':    0,
                'total_withdrawn': 0,
            })

        return Response({
            'balance':                  wallet.balance,
            'total_earned':             wallet.total_earned,
            'total_withdrawn':          wallet.total_withdrawn,
            'minimum_withdrawal_kobo':  SystemSettings.get().minimum_withdrawal_kobo,
        })


# ── Affiliate payout views ────────────────────────────────────────────────────

class PayoutRequestListView(APIView):
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        payouts = PayoutRequest.objects.filter(affiliate=request.user)

        status_filter = request.query_params.get('status')
        if status_filter:
            payouts = payouts.filter(status=status_filter)

        return Response({
            'count':   payouts.count(),
            'results': PayoutRequestSerializer(payouts, many=True).data,
        })

    def post(self, request):
        serializer = CreatePayoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        bank_account_id  = serializer.validated_data['bank_account_id']
        requested_amount = serializer.validated_data['requested_amount']

        # Verify bank account belongs to affiliate
        try:
            bank_account = BankAccount.objects.get(
                id         = bank_account_id,
                affiliate  = request.user,
                deleted_at__isnull = True,
            )
        except BankAccount.DoesNotExist:
            return Response(
                {'detail': 'Bank account not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Bank account must have a Paystack recipient code
        if not bank_account.paystack_recipient_code:
            return Response(
                {'detail': 'This bank account is not verified with Paystack. Please remove it and add it again.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Minimum payout check
        minimum_payout = SystemSettings.get().minimum_withdrawal_kobo
        if requested_amount < minimum_payout:
            return Response(
                {'detail': f'Minimum payout amount is ₦{minimum_payout / 100:,.2f}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check wallet balance covers amount + fee
        try:
            wallet = request.user.wallet
        except Exception:
            return Response(
                {'detail': 'Wallet not found.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        total_deduction = requested_amount + TRANSFER_FEE
        if wallet.balance < total_deduction:
            return Response(
                {
                    'detail': (
                        f'Insufficient balance. You need ₦{total_deduction / 100:,.2f} '
                        f'(requested amount + ₦{TRANSFER_FEE / 100:,.2f} transfer fee) '
                        f'but your balance is ₦{wallet.balance / 100:,.2f}.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Block if there is already a pending payout
        if PayoutRequest.objects.filter(
            affiliate = request.user,
            status__in = ('pending', 'approved'),
        ).exists():
            return Response(
                {'detail': 'You already have a payout request in progress.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        net_amount = requested_amount - TRANSFER_FEE

        with transaction.atomic():
            # Deduct from wallet immediately on request
            wallet = request.user.wallet
            wallet.balance         -= total_deduction
            wallet.total_withdrawn += requested_amount
            wallet.save(update_fields=['balance', 'total_withdrawn', 'updated_at'])

            payout = PayoutRequest.objects.create(
                affiliate          = request.user,
                bank_account       = bank_account,
                requested_amount   = requested_amount,
                transfer_fee       = TRANSFER_FEE,
                net_amount         = net_amount,
                balance_at_request = wallet.balance + total_deduction,
            )

        settings = SystemSettings.get()

        if settings.payout_auto_approve:
            reference = f'leyyow-payout-{payout.id}-{int(time.time())}'
            try:
                transfer_code = initiate_transfer(
                    amount_kobo = payout.net_amount,
                    recipient_code = bank_account.paystack_recipient_code,
                    reference = reference,
                    reason = 'Leyyow affiliate payout',
                )
                payout.status = 'approved'
                payout.paystack_transfer_code = transfer_code
                payout.reviewed_at = now()
                # reviewed_by stays None — signals "Auto"
                payout.save(update_fields=[
                    'status', 'paystack_transfer_code', 'reviewed_at', 'updated_at',
                ])
                log_action(
                    actor_type='affiliate', actor_id=request.user.id,
                    action='payout.auto_approved', entity_type='payout_request',
                    entity_id=payout.id,
                )
                task_send_payout_approved.delay(str(payout.id))
            except ValueError:
                # Transfer failed — leave as pending for manual review
                pass
        
        log_action(
            actor_type='affiliate', actor_id=request.user.id,
            action='payout.requested', entity_type='payout_request',
            entity_id=payout.id,
        )

        return Response(
            PayoutRequestSerializer(payout).data,
            status=status.HTTP_201_CREATED
        )


class BankListView(APIView):
    """Returns Paystack bank list. Used to populate bank dropdown."""
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        from payouts.paystack import get_banks
        try:
            banks = get_banks()
            return Response(banks)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ResolveAccountView(APIView):
    """Resolve account name from account number + bank code via Paystack."""
    authentication_classes = [AffiliateJWTAuthentication]
    permission_classes     = [IsAffiliate]

    def get(self, request):
        from payouts.paystack import resolve_account
        account_number = request.query_params.get('account_number')
        bank_code      = request.query_params.get('bank_code')

        if not account_number or not bank_code:
            return Response(
                {'detail': 'account_number and bank_code are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            account_name = resolve_account(account_number, bank_code)
            return Response({'account_name': account_name})
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        
# ── Admin payout management views ─────────────────────────────────────────────

class AdminPayoutListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        payouts = PayoutRequest.objects.select_related(
            'affiliate', 'bank_account', 'reviewed_by'
        ).order_by('-requested_at')

        status_filter = request.query_params.get('status')
        if status_filter:
            payouts = payouts.filter(status=status_filter)

        affiliate_id = request.query_params.get('affiliate_id')
        if affiliate_id:
            payouts = payouts.filter(affiliate_id=affiliate_id)

        return Response({
            'count':   payouts.count(),
            'results': AdminPayoutRequestSerializer(payouts, many=True).data,
        })


class AdminPayoutDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request, payout_id):
        try:
            payout = PayoutRequest.objects.select_related(
                'affiliate', 'bank_account', 'reviewed_by'
            ).get(id=payout_id)
        except PayoutRequest.DoesNotExist:
            return Response({'detail': 'Payout request not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response(AdminPayoutRequestSerializer(payout).data)

    def post(self, request, payout_id):
        """Admin action on a payout — approve or cancel."""
        try:
            payout = PayoutRequest.objects.select_related(
                'affiliate', 'bank_account'
            ).get(id=payout_id)
        except PayoutRequest.DoesNotExist:
            return Response({'detail': 'Payout request not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminPayoutActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action      = serializer.validated_data['action']
        admin_notes = serializer.validated_data.get('admin_notes', '')

        # ── APPROVE ───────────────────────────────────────────────────────────
        if action == 'approve':
            if payout.status != 'pending':
                return Response(
                    {'detail': 'Only pending payouts can be approved.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not payout.bank_account.paystack_recipient_code:
                return Response(
                    {'detail': 'Bank account has no Paystack recipient code. Ask the affiliate to re-add their bank account.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Initiate Paystack transfer
            # reference = f'leyyow-payout-{payout.id}'
            reference = f'leyyow-payout-{payout.id}-{int(time.time())}'
            try:
                transfer_code = initiate_transfer(
                    amount_kobo = payout.net_amount,
                    recipient_code = payout.bank_account.paystack_recipient_code,
                    reference = reference,
                    reason = 'Leyyow affiliate payout',
                )
            except ValueError as e:
                return Response(
                    {'detail': f'Paystack transfer failed: {e}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            payout.status = 'approved'
            payout.paystack_transfer_code = transfer_code
            payout.reviewed_by = request.user
            payout.reviewed_at = now()
            payout.admin_notes = admin_notes
            payout.save(update_fields=[
                'status', 'paystack_transfer_code',
                'reviewed_by', 'reviewed_at', 'admin_notes', 'updated_at',
            ])

            log_action(
                actor_type='admin', actor_id=request.user.id,
                action='payout.approved', entity_type='payout_request',
                entity_id=payout.id,
            )

            task_send_payout_approved.delay(str(payout.id))

            return Response(AdminPayoutRequestSerializer(payout).data)

        # ── CANCEL ────────────────────────────────────────────────────────────
        elif action == 'cancel':
            if payout.status not in ('pending', 'approved'):
                return Response(
                    {'detail': 'Only pending or approved payouts can be cancelled.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # If already approved, transfer is in-flight with Paystack.
            # We can't reverse it programmatically in v1 — flag it for manual follow-up.
            if payout.status == 'approved':
                return Response(
                    {'detail': 'This payout has already been sent to Paystack. Contact Paystack support to reverse the transfer, then cancel manually.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            with transaction.atomic():
                # Refund wallet
                wallet = AffiliateWallet.objects.select_for_update().get(
                    affiliate=payout.affiliate
                )
                refund_amount = payout.requested_amount + payout.transfer_fee
                wallet.balance += refund_amount
                wallet.total_withdrawn -= payout.requested_amount
                wallet.save(update_fields=['balance', 'total_withdrawn', 'updated_at'])

                payout.status = 'cancelled'
                payout.reviewed_by = request.user
                payout.reviewed_at = now()
                payout.admin_notes = admin_notes
                payout.save(update_fields=[
                    'status', 'reviewed_by', 'reviewed_at', 'admin_notes', 'updated_at',
                ])

            log_action(
                actor_type='admin', actor_id=request.user.id,
                action='payout.cancelled', entity_type='payout_request',
                entity_id=payout.id,
            )

            task_send_payout_cancelled.delay(str(payout.id))

            return Response(AdminPayoutRequestSerializer(payout).data)

        return Response({'detail': 'Invalid action.'}, status=status.HTTP_400_BAD_REQUEST)


# ── Admin central wallet view ─────────────────────────────────────────────────

class AdminCentralWalletView(APIView):
    """Central wallet balance view for Leyyow admin."""
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        from tracking.models import CentralWallet
        try:
            wallet = CentralWallet.objects.get(id=1)
            return Response({
                'balance':                     wallet.balance,
                'total_commissions_allocated': wallet.total_commissions_allocated,
                'total_payouts_made':          wallet.total_payouts_made,
                'updated_at':                  wallet.updated_at.isoformat(),
            })
        except CentralWallet.DoesNotExist:
            return Response({
                'balance':                     0,
                'total_commissions_allocated': 0,
                'total_payouts_made':          0,
            })


class AdminWalletManagementView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes     = [IsAnyAdmin]

    def get(self, request):
        from datetime import datetime

        # Central wallet
        try:
            wallet = CentralWallet.objects.get(id=1)
        except CentralWallet.DoesNotExist:
            wallet = None

        balance                     = wallet.balance if wallet else 0
        total_commissions_allocated = wallet.total_commissions_allocated if wallet else 0
        total_payouts_made          = wallet.total_payouts_made if wallet else 0
        last_updated                = wallet.updated_at.isoformat() if wallet else None

        # Total fees collected
        total_fees = PayoutRequest.objects.filter(
            status='paid'
        ).aggregate(
            total=db_models.Sum('transfer_fee')
        )['total'] or 0

        # Total reversed commissions
        total_reversed = Commission.objects.filter(
            status='reversed'
        ).aggregate(
            total=db_models.Sum('amount')
        )['total'] or 0

        # Pending disbursement
        pending_disbursement = PayoutRequest.objects.filter(
            status__in=['pending', 'approved']
        ).aggregate(
            total=db_models.Sum('net_amount')
        )['total'] or 0

        # Credited this month
        month_start = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        credited_this_month = Commission.objects.filter(
            status='earned',
            earned_at__gte=month_start,
        ).aggregate(total=db_models.Sum('amount'))['total'] or 0

        # Build transaction ledger
        events = []

        # Commission credits
        commissions = Commission.objects.select_related(
            'affiliate', 'campaign'
        ).order_by('-earned_at')

        for c in commissions:
            if c.status == 'reversed':
                events.append({
                    'id':            str(c.id) + '-rev',
                    'created_at':    c.reversed_at or c.earned_at,
                    'event_type':    'reversal',
                    'description':   f"Commission reversed — {c.campaign.name}",
                    'affiliate_name': c.affiliate.full_name,
                    'amount':        -c.amount,
                    'balance_after': None,
                    'status':        'done',
                })
            else:
                events.append({
                    'id':            str(c.id),
                    'created_at':    c.earned_at,
                    'event_type':    'credit',
                    'description':   f"Commission earned — {c.campaign.name}",
                    'affiliate_name': c.affiliate.full_name,
                    'amount':        c.amount,
                    'balance_after': None,
                    'status':        'done',
                })

        # Payout outflows
        payouts = PayoutRequest.objects.select_related(
            'affiliate', 'bank_account'
        ).order_by('-requested_at')

        for p in payouts:
            if p.status == 'paid':
                events.append({
                    'id':            str(p.id) + '-fee',
                    'created_at':    p.paid_at or p.requested_at,
                    'event_type':    'fee',
                    'description':   f"Transfer fee — {p.affiliate.full_name}",
                    'affiliate_name': p.affiliate.full_name,
                    'amount':        -p.transfer_fee,
                    'balance_after': None,
                    'status':        'done',
                })
            events.append({
                'id':            str(p.id),
                'created_at':    p.requested_at,
                'event_type':    'payout',
                'description':   f"Payout to {p.affiliate.full_name}",
                'affiliate_name': p.affiliate.full_name,
                'amount':        -p.net_amount,
                'balance_after': None,
                'status':        'done' if p.status == 'paid' else 'pending',
            })

        # Sort all events by date descending
        events.sort(key=lambda x: x['created_at'], reverse=True)

        # Stringify datetimes
        for e in events:
            if e['created_at'] and hasattr(e['created_at'], 'isoformat'):
                e['created_at'] = e['created_at'].isoformat()

        return Response({
            'balance':              balance,
            'total_credited':       total_commissions_allocated,
            'total_disbursed':      total_payouts_made,
            'total_fees':           total_fees,
            'total_reversed':       total_reversed,
            'pending_disbursement': pending_disbursement,
            'credited_this_month':  credited_this_month,
            'last_updated':         last_updated,
            'events':               events,
        })
    
# ── Paystack webhook view ─────────────────────────────────────────────────────

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name='dispatch')
class PaystackWebhookView(APIView):
    authentication_classes = []
    permission_classes     = []

    # def post(self, request):
    #     from payouts.webhooks import handle_paystack_webhook
    #     success, message = handle_paystack_webhook(request)
    #     if not success:
    #         return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)
    #     return Response({'detail': 'OK'}, status=status.HTTP_200_OK)
    
    def post(self, request):
        signature = request.headers.get('X-Paystack-Signature', '')
        print('Webhook received. Signature:', signature)
        print('Body:', request.body[:200])
        from payouts.webhooks import handle_paystack_webhook
        success, message = handle_paystack_webhook(request)
        print('Result:', success, message)
        if not success:
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'OK'}, status=status.HTTP_200_OK)