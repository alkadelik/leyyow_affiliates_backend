import hmac
import hashlib
import requests
from django.conf import settings

PAYSTACK_BASE = 'https://api.paystack.co'

def _headers():
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }

def create_recipient(bank_name, account_number, account_name, bank_code):
    """Create a Paystack transfer recipient. Returns recipient_code."""
    resp = requests.post(
        f'{PAYSTACK_BASE}/transferrecipient',
        json={
            'type':           'nuban',
            'name':           account_name,
            'account_number': account_number,
            'bank_code':      bank_code,
            'currency':       'NGN',
        },
        headers=_headers(),
        timeout=30,
    )
    data = resp.json()
    if not data.get('status'):
        raise ValueError(data.get('message', 'Failed to create recipient'))
    return data['data']['recipient_code']


def initiate_transfer(amount_kobo, recipient_code, reference, reason='Affiliate payout'):
    """Initiate a transfer. Returns transfer_code."""
    resp = requests.post(
        f'{PAYSTACK_BASE}/transfer',
        json={
            'source':    'balance',
            'amount':    amount_kobo,
            'recipient': recipient_code,
            'reason':    reason,
            'reference': reference,
        },
        headers=_headers(),
        timeout=30,
    )
    data = resp.json()
    if not data.get('status'):
        raise ValueError(data.get('message', 'Failed to initiate transfer'))
    return data['data']['transfer_code']


def get_banks():
    """Fetch list of Nigerian banks from Paystack."""
    resp = requests.get(
        f'{PAYSTACK_BASE}/bank?currency=NGN&per_page=100',
        headers=_headers(),
        timeout=30,
    )
    data = resp.json()
    if not data.get('status'):
        raise ValueError('Failed to fetch banks')
    return data['data']  # list of {name, code, ...}


def resolve_account(account_number, bank_code):
    """Resolve account name from account number + bank code."""
    resp = requests.get(
        f'{PAYSTACK_BASE}/bank/resolve',
        params={'account_number': account_number, 'bank_code': bank_code},
        headers=_headers(),
        timeout=30,
    )
    data = resp.json()
    if not data.get('status'):
        raise ValueError(data.get('message', 'Could not resolve account'))
    return data['data']['account_name']


def verify_webhook(payload_bytes, signature):
    """Verify Paystack webhook signature."""
    secret = settings.PAYSTACK_SECRET_KEY.encode('utf-8')
    expected = hmac.new(secret, payload_bytes, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)