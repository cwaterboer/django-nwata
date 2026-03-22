"""Entitlement resolution for dashboard feature gating."""

from api.models import Membership
from api.permissions import get_user_permissions_in_org, get_user_role_in_org


def resolve_dashboard_entitlements(auth_user, organization):
    """Return normalized entitlement flags for dashboard monetization gates."""
    entitlements = {
        "has_active_membership": False,
        "license_type": "individual",
        "role": None,
        "can_manage_billing": False,
        "can_export_team_data": False,
        "can_access_premium_analytics": False,
    }

    if not auth_user or not auth_user.is_authenticated or not organization:
        return entitlements

    membership = Membership.objects.filter(
        auth_user=auth_user,
        organization=organization,
        status="active",
    ).first()

    if membership:
        entitlements["has_active_membership"] = True
        entitlements["license_type"] = membership.license_type
        entitlements["role"] = membership.role

        # Owner can always manage billing in the current role model.
        entitlements["can_manage_billing"] = membership.role == "owner"

        # Team exports are available only on team licenses for elevated roles.
        entitlements["can_export_team_data"] = (
            membership.license_type == "team" and membership.role in {"owner", "admin"}
        )
    else:
        # Legacy RBAC fallback for accounts still mapped through UserOrgRole.
        role = get_user_role_in_org(auth_user, organization)
        permissions = set(get_user_permissions_in_org(auth_user, organization))

        entitlements["role"] = role.name if role else None
        entitlements["can_manage_billing"] = "manage_billing" in permissions
        entitlements["can_export_team_data"] = "export_team_data" in permissions

    entitlements["can_access_premium_analytics"] = (
        entitlements["license_type"] == "team"
        and (entitlements["can_manage_billing"] or entitlements["can_export_team_data"])
    )

    return entitlements
