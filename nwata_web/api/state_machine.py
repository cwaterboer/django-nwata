"""
State machine logic for organization lifecycle management
"""
from django.utils import timezone
from .models import OrganizationState, AuditLog


class OrganizationStateMachine:
    """Manages organization state transitions with validation and audit logging"""
    
    VALID_TRANSITIONS = {
        'created': ['active', 'archived'],
        'active': ['suspended', 'archived'],
        'suspended': ['active', 'archived'],
        'archived': [],  # Terminal state
    }
    
    @classmethod
    def can_transition(cls, current_state, new_state):
        """Check if a state transition is valid"""
        return new_state in cls.VALID_TRANSITIONS.get(current_state, [])
    
    @classmethod
    def activate_organization(cls, org_state, user=None, reason=''):
        """
        Transition organization to active state
        Typically called after first successful payment
        """
        if org_state.current_state == 'active':
            return False  # Already active
        
        if not cls.can_transition(org_state.current_state, 'active'):
            raise ValueError(f"Cannot activate organization from {org_state.current_state} state")
        
        previous_state = org_state.current_state
        org_state.transition_to('active', user=user, reason=reason)
        
        # Audit log
        AuditLog.objects.create(
            actor=user,
            actor_email=user.email if user else 'system',
            action='org.state_changed',
            resource_type='organization',
            resource_id=org_state.organization.id,
            organization=org_state.organization,
            changes_before={'state': previous_state},
            changes_after={'state': 'active'},
        )
        
        return True
    
    @classmethod
    def suspend_organization(cls, org_state, user=None, reason=''):
        """
        Suspend organization (e.g., payment delinquency)
        Users lose access but data is preserved
        """
        if not cls.can_transition(org_state.current_state, 'suspended'):
            raise ValueError(f"Cannot suspend organization from {org_state.current_state} state")
        
        previous_state = org_state.current_state
        org_state.transition_to('suspended', user=user, reason=reason)
        
        # Audit log
        AuditLog.objects.create(
            actor=user,
            actor_email=user.email if user else 'system',
            action='org.state_changed',
            resource_type='organization',
            resource_id=org_state.organization.id,
            organization=org_state.organization,
            changes_before={'state': previous_state},
            changes_after={'state': 'suspended', 'reason': reason},
        )
        
        # TODO: Disable user access, send notifications
        
        return True
    
    @classmethod
    def archive_organization(cls, org_state, user=None, reason=''):
        """
        Archive organization permanently
        Terminal state - cannot be reversed
        """
        if not cls.can_transition(org_state.current_state, 'archived'):
            raise ValueError(f"Cannot archive organization from {org_state.current_state} state")
        
        previous_state = org_state.current_state
        org_state.transition_to('archived', user=user, reason=reason)
        
        # Audit log
        AuditLog.objects.create(
            actor=user,
            actor_email=user.email if user else 'system',
            action='org.state_changed',
            resource_type='organization',
            resource_id=org_state.organization.id,
            organization=org_state.organization,
            changes_before={'state': previous_state},
            changes_after={'state': 'archived', 'reason': reason},
        )
        
        # TODO: Schedule data deletion, revoke all access, cancel subscriptions
        
        return True


class UserInvitationStateMachine:
    """Manages user invitation workflow"""
    
    VALID_TRANSITIONS = {
        'pending': ['invited', 'active', 'inactive'],
        'invited': ['active', 'inactive'],
        'active': ['suspended', 'inactive'],
        'suspended': ['active', 'inactive'],
        'inactive': [],  # Terminal state
    }
    
    @classmethod
    def can_transition(cls, current_state, new_state):
        """Check if a state transition is valid"""
        return new_state in cls.VALID_TRANSITIONS.get(current_state, [])
    
    @classmethod
    def send_invitation(cls, user_org_role, invited_by=None):
        """
        Send invitation to user
        Generates token and sets expiry
        """
        if user_org_role.state not in ['pending', 'inactive']:
            raise ValueError(f"Cannot send invitation from {user_org_role.state} state")
        
        user_org_role.generate_invitation_token()
        user_org_role.invited_by = invited_by
        user_org_role.save()
        
        # Audit log
        AuditLog.objects.create(
            actor=invited_by,
            actor_email=invited_by.email if invited_by else 'system',
            action='user.invited',
            resource_type='user',
            resource_id=user_org_role.user.id,
            organization=user_org_role.organization,
            changes_after={
                'email': user_org_role.user.email,
                'role': user_org_role.role.name,
                'invited_at': user_org_role.invited_at.isoformat() if user_org_role.invited_at else None,
            },
        )
        
        # TODO: Send email with invitation link
        
        return True
    
    @classmethod
    def accept_invitation(cls, user_org_role):
        """
        User accepts invitation
        Validates token and activates user
        """
        if not user_org_role.is_invitation_valid():
            raise ValueError("Invitation token is invalid or expired")
        
        user_org_role.accept_invitation()
        
        # Audit log
        AuditLog.objects.create(
            actor=user_org_role.user,
            actor_email=user_org_role.user.email,
            action='user.accepted_invitation',
            resource_type='user',
            resource_id=user_org_role.user.id,
            organization=user_org_role.organization,
            changes_before={'state': 'invited'},
            changes_after={'state': 'active'},
        )
        
        return True
    
    @classmethod
    def suspend_user(cls, user_org_role, suspended_by=None, reason=''):
        """Suspend user access"""
        if not cls.can_transition(user_org_role.state, 'suspended'):
            raise ValueError(f"Cannot suspend user from {user_org_role.state} state")
        
        previous_state = user_org_role.state
        user_org_role.state = 'suspended'
        user_org_role.save()
        
        # Audit log
        AuditLog.objects.create(
            actor=suspended_by,
            actor_email=suspended_by.email if suspended_by else 'system',
            action='user.suspended',
            resource_type='user',
            resource_id=user_org_role.user.id,
            organization=user_org_role.organization,
            changes_before={'state': previous_state},
            changes_after={'state': 'suspended', 'reason': reason},
        )
        
        return True
    
    @classmethod
    def remove_user(cls, user_org_role, removed_by=None, reason=''):
        """Remove user from organization"""
        if user_org_role.state == 'inactive':
            return False  # Already removed
        
        previous_state = user_org_role.state
        user_org_role.state = 'inactive'
        user_org_role.save()
        
        # Audit log
        AuditLog.objects.create(
            actor=removed_by,
            actor_email=removed_by.email if removed_by else 'system',
            action='user.removed',
            resource_type='user',
            resource_id=user_org_role.user.id,
            organization=user_org_role.organization,
            changes_before={'state': previous_state},
            changes_after={'state': 'inactive', 'reason': reason},
        )
        
        return True
