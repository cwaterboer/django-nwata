"""
Django signals for automatic audit logging and data quality monitoring
"""
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
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
    This provides daily aggregated metrics for monitoring and ML preparation.
    """
    from django.db.models import Avg, Count, Q
    
    # Only process if quality score was computed
    if not instance.data_quality_score:
        return
    
    # Get the date for this activity (its end_time date)
    log_date = instance.end_time.date()
    org = instance.user.org
    
    # Get or create daily metrics for this org
    metrics, _ = DataQualityMetrics.objects.get_or_create(
        date=log_date,
        organization=org
    )
    
    # Recalculate aggregates for the day
    day_logs = ActivityLog.objects.filter(
        user__org=org,
        end_time__date=log_date
    )
    
    total = day_logs.count()
    valid = day_logs.filter(data_quality_score__gte=0.7).count()
    with_context = day_logs.filter(context__isnull=False).count()
    
    # Aggregate quality scores
    agg = day_logs.aggregate(
        avg_quality=Avg('data_quality_score'),
        min_quality=Avg('data_quality_score'),  # Will refine below
        max_quality=Avg('data_quality_score'),  # Will refine below
    )
    
    # Get min/max properly
    quality_values = day_logs.values_list('data_quality_score', flat=True)
    if quality_values:
        min_q = min(quality_values)
        max_q = max(quality_values)
        avg_q = sum(quality_values) / len(quality_values)
    else:
        min_q = max_q = avg_q = 0.0
    
    # Aggregate normalized context metrics
    normalized_values = day_logs.filter(
        normalized_context__isnull=False
    ).values_list('normalized_context', flat=True)
    
    avg_idle = avg_typing = avg_intensity = 0.0
    if normalized_values:
        idle_ratios = []
        typing_rates = []
        intensities = []
        
        for nc in normalized_values:
            if nc:
                idle_ratios.append(nc.get('idle_ratio', 0))
                typing_rates.append(nc.get('typing_rate_per_min', 0))
                intensities.append(nc.get('activity_intensity', 0))
        
        if idle_ratios:
            avg_idle = sum(idle_ratios) / len(idle_ratios)
        if typing_rates:
            avg_typing = sum(typing_rates) / len(typing_rates)
        if intensities:
            avg_intensity = sum(intensities) / len(intensities)
    
    # Count schema violations (logs with validation_errors)
    violations = day_logs.filter(validation_errors__isnull=False).count()
    
    # Update metrics
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
    
    metrics.save(update_fields=[
        'total_logs', 'valid_logs', 'schema_violations', 'logs_with_context',
        'avg_data_quality_score', 'min_data_quality_score', 'max_data_quality_score',
        'avg_idle_ratio', 'avg_typing_rate_per_min', 'avg_activity_intensity',
        'quality_degradation_flag', 'high_violation_rate_flag'
    ])

