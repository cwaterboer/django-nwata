"""
Django signals for automatic audit logging
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from .models import UserOrgRole, Organization, OrganizationState, Department, AuditLog


@receiver(post_save, sender=UserOrgRole)
def log_user_org_role_change(sender, instance, created, **kwargs):
    """Log when user role is created or changed"""
    if created:
        action = 'user.created'
        changes_before = None
        changes_after = {
            'user': instance.user.email,
            'organization': instance.organization.name,
            'role': instance.role.name,
            'state': instance.state,
        }
    else:
        action = 'user.role_changed'
        # Get previous values from database
        try:
            old_instance = UserOrgRole.objects.get(pk=instance.pk)
            changes_before = {
                'role': old_instance.role.name,
                'state': old_instance.state,
            }
            changes_after = {
                'role': instance.role.name,
                'state': instance.state,
            }
        except UserOrgRole.DoesNotExist:
            changes_before = None
            changes_after = None
    
    # Don't log if no actor available (system changes)
    if not instance.invited_by:
        return
    
    AuditLog.objects.create(
        actor=instance.invited_by,
        actor_email=instance.invited_by.email if instance.invited_by else 'system',
        action=action,
        resource_type='user_org_role',
        resource_id=instance.id,
        organization=instance.organization,
        changes_before=changes_before,
        changes_after=changes_after,
    )


@receiver(post_save, sender=Organization)
def log_organization_change(sender, instance, created, **kwargs):
    """Log when organization is created or modified"""
    if created:
        AuditLog.objects.create(
            actor=None,
            actor_email='system',
            action='org.created',
            resource_type='organization',
            resource_id=instance.id,
            organization=instance,
            changes_after={
                'name': instance.name,
                'subdomain': instance.subdomain,
                'organization_type': instance.organization_type,
            },
        )


@receiver(post_save, sender=OrganizationState)
def log_organization_state_change(sender, instance, created, **kwargs):
    """Log organization state transitions"""
    if not created and instance.previous_state:
        AuditLog.objects.create(
            actor=instance.state_changed_by,
            actor_email=instance.state_changed_by.email if instance.state_changed_by else 'system',
            action='org.state_changed',
            resource_type='organization_state',
            resource_id=instance.id,
            organization=instance.organization,
            changes_before={'state': instance.previous_state},
            changes_after={
                'state': instance.current_state,
                'reason': instance.reason,
            },
        )


@receiver(post_save, sender=Department)
def log_department_change(sender, instance, created, **kwargs):
    """Log department creation and changes"""
    if created:
        AuditLog.objects.create(
            actor=None,
            actor_email='system',
            action='dept.created',
            resource_type='department',
            resource_id=instance.id,
            organization=instance.organization,
            changes_after={
                'name': instance.name,
                'parent': instance.parent_department.name if instance.parent_department else None,
                'manager': instance.manager.email if instance.manager else None,
            },
        )


@receiver(pre_delete, sender=Department)
def log_department_deletion(sender, instance, **kwargs):
    """Log department deletion"""
    AuditLog.objects.create(
        actor=None,
        actor_email='system',
        action='dept.deleted',
        resource_type='department',
        resource_id=instance.id,
        organization=instance.organization,
        changes_before={
            'name': instance.name,
            'parent': instance.parent_department.name if instance.parent_department else None,
        },
    )
