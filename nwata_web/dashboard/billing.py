"""Billing and subscription primitives for staged monetization rollout."""

from datetime import timedelta
from django.utils import timezone
from api.models import OrganizationState


GRACE_PERIOD_DAYS = 7


def build_subscription_snapshot(organization, entitlements):
    """Build a normalized subscription snapshot from org + entitlement state."""
    snapshot = {
        "plan": "free-individual",
        "status": "active",
        "grace_until": None,
        "can_use_premium_analytics": entitlements.get("can_access_premium_analytics", False),
    }

    if not organization:
        return snapshot

    license_type = entitlements.get("license_type", "individual")
    snapshot["plan"] = "pro-team" if license_type == "team" else "free-individual"

    try:
        org_state = OrganizationState.objects.get(organization=organization)
    except OrganizationState.DoesNotExist:
        return snapshot

    if org_state.current_state == "suspended":
        snapshot["status"] = "grace"
        state_changed_at = org_state.state_changed_at or timezone.now()
        snapshot["grace_until"] = state_changed_at + timedelta(days=GRACE_PERIOD_DAYS)
    elif org_state.current_state == "archived":
        snapshot["status"] = "inactive"

    return snapshot
