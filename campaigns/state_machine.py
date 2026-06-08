from django.utils.timezone import now
from django.core.exceptions import ValidationError


VALID_TRANSITIONS = {
    'draft':     ['scheduled', 'active', 'cancelled'],
    'scheduled': ['active', 'cancelled'],
    'active':    ['ended', 'cancelled'],
    'ended':     [],
    'cancelled': [],
}


def can_transition(campaign, target_status):
    """Check if a transition is valid. Returns (True, None) or (False, reason)."""
    current = campaign.status

    if target_status in ('scheduled', 'active'):
        if not campaign.starts_at:
            return False, "Campaign must have a start date before it can be started."
        if campaign.commission_type == 'percentage_capped' and not campaign.commission_cap:
            return False, "A commission cap is required for percentage_capped campaigns."
        if not campaign.commission_trigger:
            return False, "Campaign must have a commission trigger before it can be started."
        if not campaign.commission_value:
            return False, "Campaign must have a commission value before it can be started."
        # ADD: block if start date has already passed
        if campaign.starts_at.date() < now().date():
            return False, "Start date has passed. Please update the start date before starting."
        # ADD: block if end date has already passed
        if campaign.ends_at and campaign.ends_at.date() < now().date():
            return False, "End date has passed. Please update the end date before starting."

    if target_status == 'scheduled':
        if campaign.starts_at.date() < now().date():
            return False, "Start date cannot be in the past."

    if target_status == 'active' and current == 'scheduled':
        if campaign.starts_at and campaign.starts_at.date() > now().date():
            return False, "Campaign start date has not been reached yet."

    return True, None


def transition(campaign, target_status, performed_by=None):
    """
    Execute a state transition. Raises ValidationError if invalid.
    Does not save — caller is responsible for saving.
    """
    ok, reason = can_transition(campaign, target_status)
    if not ok:
        raise ValidationError(reason)

    campaign.status = target_status

    if target_status == 'cancelled':
        campaign.cancelled_at = now()
        campaign.cancelled_by = performed_by

    if target_status == 'ended':
        campaign.ended_at = now()