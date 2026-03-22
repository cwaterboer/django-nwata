"""
Django signals for automatic audit logging and data quality monitoring
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.conf import settings
from django.utils import timezone
from datetime import datetime, date
from .models import UserOrgRole, Organization, OrganizationState, Department, AuditLog, ActivityLog, DataQualityMetrics


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


# ========================================
# DATA QUALITY MONITORING SIGNALS
# ========================================

@receiver(post_save, sender=ActivityLog)
def update_data_quality_metrics(sender, instance, created, **kwargs):
    """
    Real-time update of data quality metrics when ActivityLog is saved.
    Optimized to minimize database queries and handle connection issues gracefully.
    """
    from django.db.models import Avg, Count, Q, Min, Max
    from django.db import transaction, connection
    from django.db import OperationalError
    
    # Only process if quality score was computed and we can resolve an org
    if instance.data_quality_score is None:
        return

    # Support both legacy `user` org linkage and new `membership` linkage.
    # Some logs may have `user=None` but still have `membership` set.
    org = None
    if hasattr(instance, 'user') and instance.user and getattr(instance.user, 'org', None):
        org = instance.user.org
    elif hasattr(instance, 'membership') and instance.membership and getattr(instance.membership, 'organization', None):
        org = instance.membership.organization

    if not org:
        return

    # Get the date for this activity (its end_time date)
    log_date = instance.end_time.date()

    try:
        # Use atomic transaction to ensure consistency
        with transaction.atomic():
            # Get or create daily metrics for this org (efficient single query)
            metrics, created = DataQualityMetrics.objects.get_or_create(
                date=log_date,
                organization=org,
                defaults={
                    'total_logs': 0,
                    'valid_logs': 0,
                    'schema_violations': 0,
                    'avg_data_quality_score': 0.0,
                    'min_data_quality_score': 0.0,
                    'max_data_quality_score': 1.0,
                    'logs_with_context': 0,
                    'avg_idle_ratio': 0.0,
                    'avg_typing_rate_per_min': 0.0,
                    'avg_activity_intensity': 0.0,
                }
            )

            # Single optimized query to get all aggregates
            day_logs = ActivityLog.objects.filter(
                user__org=org,
                end_time__date=log_date
            )

            # Use database aggregation for efficiency
            aggregates = day_logs.aggregate(
                total=Count('id'),
                valid=Count('id', filter=Q(data_quality_score__gte=0.7)),
                with_context=Count('id', filter=Q(context__isnull=False)),
                avg_quality=Avg('data_quality_score'),
                min_quality=Min('data_quality_score'),
                max_quality=Max('data_quality_score'),
            )

            # Extract values with defaults
            total = aggregates.get('total', 0)
            valid = aggregates.get('valid', 0)
            with_context = aggregates.get('with_context', 0)
            avg_q = aggregates.get('avg_quality', 0.0) or 0.0
            min_q = aggregates.get('min_quality', 0.0) or 0.0
            max_q = aggregates.get('max_quality', 1.0) or 1.0

            # For JSON field aggregation, use Python processing to avoid database-specific issues
            avg_idle = avg_typing = avg_intensity = 0.0

            # Limit processing to avoid memory issues - only process last 100 logs
            try:
                recent_normalized = list(day_logs.filter(normalized_context__isnull=False).order_by('-id')[:100].values_list('normalized_context', flat=True))

                if recent_normalized:
                    idle_ratios = []
                    typing_rates = []
                    intensities = []

                    for nc in recent_normalized:
                        if isinstance(nc, dict):
                            idle_ratios.append(nc.get('idle_ratio', 0))
                            typing_rates.append(nc.get('typing_rate_per_min', 0))
                            intensities.append(nc.get('activity_intensity', 0))

                    if idle_ratios:
                        avg_idle = sum(idle_ratios) / len(idle_ratios)
                    if typing_rates:
                        avg_typing = sum(typing_rates) / len(typing_rates)
                    if intensities:
                        avg_intensity = sum(intensities) / len(intensities)
            except Exception as e:
                # Continue with zeros
                pass

            # Count schema violations (logs with validation_errors)
            violations = day_logs.filter(validation_errors__isnull=False).count()

            # Update metrics atomically
            metrics.total_logs = total
            metrics.valid_logs = valid
            metrics.schema_violations = violations
            metrics.logs_with_context = with_context
            metrics.avg_data_quality_score = round(avg_q, 3)
            metrics.min_data_quality_score = round(min_q, 3)
            metrics.max_data_quality_score = round(max_q, 3)
            metrics.avg_idle_ratio = round(avg_idle, 3)
            metrics.avg_typing_rate_per_min = round(avg_typing, 2)
            metrics.avg_activity_intensity = round(avg_intensity, 2)

            # Set alert flags
            metrics.quality_degradation_flag = avg_q < 0.75
            violation_rate = (violations / total) if total > 0 else 0
            metrics.high_violation_rate_flag = violation_rate > 0.10  # 10% threshold

            # Save with update_fields for efficiency
            metrics.save(update_fields=[
                'total_logs', 'valid_logs', 'schema_violations', 'logs_with_context',
                'avg_data_quality_score', 'min_data_quality_score', 'max_data_quality_score',
                'avg_idle_ratio', 'avg_typing_rate_per_min', 'avg_activity_intensity',
                'quality_degradation_flag', 'high_violation_rate_flag'
            ])

    except OperationalError as e:
        # Handle database connection issues gracefully
        # Log but don't fail the request
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Database connection issue in data quality signal: {e}")
        # Could implement retry logic or queue for later processing here

    except Exception as e:
        # Catch any other unexpected errors to prevent request failures
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error in data quality signal: {e}", exc_info=True)


# ==========================================
# NOTIFICATION SIGNALS
# ==========================================

@receiver(post_save, sender='api.Membership')
def trigger_user_added_notification(sender, instance, created, **kwargs):
    """
    Trigger notification when user is added to organization.
    Fires when Membership.status changes to 'active'.
    """
    from .tasks import send_user_added_notification
    
    if not getattr(settings, 'ENABLE_ASYNC_SIGNAL_DISPATCH', False):
        return

    if created and instance.status == 'active':
        # Async task to send notifications to all members
        send_user_added_notification.delay(
            organization_id=instance.organization.id,
            new_user_id=instance.auth_user.id,
            added_by_id=instance.created_by.id if hasattr(instance, 'created_by') and instance.created_by else 1
        )


@receiver(pre_delete, sender='api.Membership')
def trigger_user_removed_notification(sender, instance, **kwargs):
    """
    Trigger notification when user is removed from organization.
    Fires before Membership is deleted.
    """
    from .tasks import send_user_removed_notification
    
    if not getattr(settings, 'ENABLE_ASYNC_SIGNAL_DISPATCH', False):
        return

    if instance.status == 'active':
        # Get the user who initiated the removal (from context if available)
        removed_by_id = getattr(instance, '_removed_by_id', 1)
        
        send_user_removed_notification.delay(
            organization_id=instance.organization.id,
            removed_user_email=instance.auth_user.email,
            removed_by_id=removed_by_id
        )

