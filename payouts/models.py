import uuid
from django.db import models


class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affiliate = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.PROTECT,
        related_name='bank_accounts'
    )
    bank_name = models.CharField(max_length=128)
    bank_code = models.CharField(max_length=16)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=255)
    is_default = models.BooleanField(default=False)
    paystack_recipient_code = models.CharField(max_length=64, null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bank_accounts'
        ordering = ['-created_at']


class PayoutRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('approved',  'Approved'),
        ('paid',      'Paid'),
        ('failed',    'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affiliate = models.ForeignKey(
        'accounts.Affiliate',
        on_delete=models.PROTECT,
        related_name='payout_requests'
    )
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='payout_requests'
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    requested_amount = models.IntegerField()
    transfer_fee = models.IntegerField(default=10000)
    net_amount = models.IntegerField()
    balance_at_request = models.IntegerField()
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        'accounts.Admin', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_payouts',
        db_column='reviewed_by'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paystack_transfer_code = models.CharField(max_length=64, null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)
    admin_notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payout_requests'
        ordering = ['-requested_at']