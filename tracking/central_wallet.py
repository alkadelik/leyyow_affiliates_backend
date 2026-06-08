# from django.db import transaction
from tracking.models import CentralWallet

def _get_or_create_central_wallet():
    """Get the single central wallet row, creating it if it doesn't exist."""
    wallet, _ = CentralWallet.objects.get_or_create(id=1)
    return wallet


def credit_central_wallet(commission):
    """Credit the central wallet when a commission is earned."""
    from tracking.models import CentralWalletEvent
    wallet = CentralWallet.objects.select_for_update().get(id=1)
    wallet.balance += commission.amount
    wallet.total_commissions_allocated += commission.amount
    wallet.save(update_fields=['balance', 'total_commissions_allocated', 'updated_at'])

    CentralWalletEvent.objects.create(
        event_type = 'credit',
        amount = commission.amount,
        balance_after = wallet.balance,
        description = f'Commission earned — {commission.campaign.name}',
        affiliate = commission.affiliate,
        commission = commission,
        status = 'done',
    )


def debit_central_wallet(commission):
    """Debit the central wallet when a commission is reversed."""
    from tracking.models import CentralWalletEvent
    wallet = CentralWallet.objects.select_for_update().get(id=1)
    wallet.balance -= commission.amount
    wallet.total_commissions_allocated -= commission.amount
    wallet.save(update_fields=['balance', 'total_commissions_allocated', 'updated_at'])

    CentralWalletEvent.objects.create(
        event_type = 'reversal',
        amount = -commission.amount,
        balance_after = wallet.balance,
        description = f'Commission reversed — {commission.campaign.name}',
        affiliate = commission.affiliate,
        commission = commission,
        status = 'done',
    )


def record_payout_event(payout):
    """Record a payout disbursement and fee in the central wallet ledger."""
    from tracking.models import CentralWalletEvent
    wallet = CentralWallet.objects.select_for_update().get(id=1)
    wallet.balance          -= payout.net_amount + payout.transfer_fee
    wallet.total_payouts_made += payout.net_amount
    wallet.save(update_fields=['balance', 'total_payouts_made', 'updated_at'])

    # Payout outflow
    CentralWalletEvent.objects.create(
        event_type = 'payout',
        amount = -payout.net_amount,
        balance_after = wallet.balance + payout.transfer_fee,  # before fee deduction
        description = f'Payout to {payout.affiliate.full_name}',
        affiliate = payout.affiliate,
        payout_request = payout,
        status = 'done',
    )

    # Fee
    CentralWalletEvent.objects.create(
        event_type = 'fee',
        amount = -payout.transfer_fee,
        balance_after = wallet.balance,
        description = f'Transfer fee — {payout.affiliate.full_name}',
        affiliate = payout.affiliate,
        payout_request = payout,
        status = 'done',
    )