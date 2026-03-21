"""
Celery tasks for handling notifications and async operations.
"""

from celery import shared_task
from django.utils import timezone
from django.contrib.auth.models import User as AuthUser
from .models import Notification, Invite, Membership, Organization
from django.core.mail import send_mail
from django.template.loader import render_to_string
import logging

logger = logging.getLogger(__name__)


# ==========================================
# NOTIFICATION TASKS
# ==========================================

@shared_task(bind=True, max_retries=3)
def send_user_added_notification(self, organization_id, new_user_id, added_by_id):
    """
    Send notification when a user is added to an organization.
    Called by signal when Membership.status changes to 'active'
    """
    try:
        organization = Organization.objects.get(id=organization_id)
        new_user = AuthUser.objects.get(id=new_user_id)
        added_by = AuthUser.objects.get(id=added_by_id)
        
        # Get all active members to notify
        active_members = Membership.objects.filter(
            organization=organization,
            status='active'
        ).exclude(auth_user=new_user).values_list('auth_user', flat=True)
        
        # Create notifications for all members
        notifications = []
        for member_id in active_members:
            member = AuthUser.objects.get(id=member_id)
            notification = Notification.objects.create(
                recipient=member,
                organization=organization,
                notification_type='user_added',
                title=f'{new_user.first_name or new_user.email} joined {organization.name}',
                message=f'{new_user.email} has been added to {organization.name} by {added_by.email}',
                actor=added_by,
                related_user=new_user,
                metadata={
                    'member_name': new_user.get_full_name() or new_user.email,
                    'member_email': new_user.email,
                    'added_by_name': added_by.get_full_name() or added_by.email,
                }
            )
            notifications.append(notification)
        
        logger.info(f"Created {len(notifications)} notifications for user {new_user.email} added to {organization.name}")
        return len(notifications)
        
    except Exception as exc:
        logger.error(f"Error sending user_added notification: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=10 ** self.request.retries)


@shared_task(bind=True, max_retries=3)
def send_role_changed_notification(self, membership_id, old_role, new_role, changed_by_id):
    """
    Send notification when user's role is changed.
    """
    try:
        from .models import Membership
        membership = Membership.objects.get(id=membership_id)
        changed_by = AuthUser.objects.get(id=changed_by_id)
        
        # Notify the user whose role changed
        Notification.objects.create(
            recipient=membership.auth_user,
            organization=membership.organization,
            notification_type='user_role_changed',
            title=f'Your role in {membership.organization.name} has changed',
            message=f'Your role was changed from {old_role} to {new_role} by {changed_by.email}',
            actor=changed_by,
            related_user=membership.auth_user,
            metadata={
                'old_role': old_role,
                'new_role': new_role,
                'changed_by': changed_by.email,
            }
        )
        
        # Notify organization admins
        admin_members = Membership.objects.filter(
            organization=membership.organization,
            status='active',
            role='admin'
        ).values_list('auth_user', flat=True)
        
        for admin_id in admin_members:
            admin_user = AuthUser.objects.get(id=admin_id)
            if admin_user != membership.auth_user:  # Don't notify the user whose role changed
                Notification.objects.create(
                    recipient=admin_user,
                    organization=membership.organization,
                    notification_type='user_role_changed',
                    title=f'{membership.auth_user.email} role updated in {membership.organization.name}',
                    message=f'{membership.auth_user.email} role was changed from {old_role} to {new_role}',
                    actor=changed_by,
                    related_user=membership.auth_user,
                    metadata={
                        'member_email': membership.auth_user.email,
                        'old_role': old_role,
                        'new_role': new_role,
                    }
                )
        
        logger.info(f"Created role_changed notifications for membership {membership_id}")
        return True
        
    except Exception as exc:
        logger.error(f"Error sending role_changed notification: {exc}")
        raise self.retry(exc=exc, countdown=10 ** self.request.retries)


@shared_task(bind=True, max_retries=3)
def send_user_removed_notification(self, organization_id, removed_user_email, removed_by_id):
    """
    Send notification when a user is removed from organization.
    """
    try:
        organization = Organization.objects.get(id=organization_id)
        removed_by = AuthUser.objects.get(id=removed_by_id)
        
        # Notify all active members except the removed user
        active_members = Membership.objects.filter(
            organization=organization,
            status='active'
        ).exclude(auth_user__email=removed_user_email).values_list('auth_user', flat=True)
        
        notifications_created = 0
        for member_id in active_members:
            member = AuthUser.objects.get(id=member_id)
            Notification.objects.create(
                recipient=member,
                organization=organization,
                notification_type='user_removed',
                title=f'{removed_user_email} removed from {organization.name}',
                message=f'{removed_user_email} has been removed from {organization.name} by {removed_by.email}',
                actor=removed_by,
                metadata={
                    'removed_email': removed_user_email,
                    'removed_by': removed_by.email,
                }
            )
            notifications_created += 1
        
        logger.info(f"Created {notifications_created} notifications for user {removed_user_email} removed from {organization.name}")
        return notifications_created
        
    except Exception as exc:
        logger.error(f"Error sending user_removed notification: {exc}")
        raise self.retry(exc=exc, countdown=10 ** self.request.retries)


@shared_task(bind=True, max_retries=3)
def send_invite_notification(self, invite_id):
    """
    Send email notification when user is invited.
    """
    try:
        invite = Invite.objects.select_related('organization', 'invited_by').get(id=invite_id)
        
        # Prepare context for email
        context = {
            'email': invite.invited_email,
            'organization_name': invite.organization.name,
            'invited_by': invite.invited_by.email,
            'invite_link': invite.token,  # In production, build full URL
        }
        
        # Render email
        subject = f"You're invited to {invite.organization.name} on Nwata"
        html_message = render_to_string('emails/invitation.html', context)
        
        # Send email
        send_mail(
            subject,
            f"You've been invited to join {invite.organization.name} on Nwata",
            'noreply@nwata.app',
            [invite.invited_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        invite.status = 'sent'
        invite.save(update_fields=['status'])
        
        logger.info(f"Sent invitation email to {invite.invited_email}")
        return True
        
    except Exception as exc:
        logger.error(f"Error sending invite email: {exc}")
        raise self.retry(exc=exc, countdown=10 ** self.request.retries)


# ==========================================
# CLEANUP TASKS
# ==========================================

@shared_task
def cleanup_expired_invitations():
    """
    Delete invitations older than 7 days that were never accepted.
    Runs daily at 2 AM.
    """
    from datetime import timedelta
    cutoff_date = timezone.now() - timedelta(days=7)
    
    expired = Invite.objects.filter(
        status__in=['pending', 'sent'],
        created_at__lt=cutoff_date
    )
    
    count, _ = expired.delete()
    logger.info(f"Cleaned up {count} expired invitations")
    return count


@shared_task
def cleanup_old_notifications():
    """
    Soft delete read notifications older than 30 days.
    Runs daily at 3 AM.
    """
    from datetime import timedelta
    cutoff_date = timezone.now() - timedelta(days=30)
    
    old_notifications = Notification.objects.filter(
        is_read=True,
        read_at__lt=cutoff_date,
        is_deleted=False
    )
    
    count = 0
    for notif in old_notifications:
        notif.soft_delete()
        count += 1
    
    logger.info(f"Soft deleted {count} old notifications")
    return count


# ==========================================
# DEBUG TASKS
# ==========================================

@shared_task
def debug_task():
    """Debug task for testing Celery setup"""
    logger.info("Debug task executed successfully")
    return "Debug task completed"
