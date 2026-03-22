from django.contrib import admin
from .models import (
    APIKey,
    ActivityLog,
    AuditLog,
    DataQualityMetrics,
    Department,
    Device,
    DeviceEvent,
    Gamification,
    Invite,
    Membership,
    Notification,
    Organization,
    OrganizationState,
    Permission,
    Role,
    RolePermission,
    User,
    UserDepartment,
    UserOrgRole,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'subdomain', 'organization_type', 'created_at']
    search_fields = ['name', 'subdomain']
    list_filter = ['organization_type', 'created_at']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'org', 'created_at']
    search_fields = ['email', 'org__name']
    list_filter = ['org', 'created_at']
    raw_id_fields = ['org']


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ['email_used', 'auth_user', 'organization', 'role', 'license_type', 'status', 'created_at']
    search_fields = ['email_used', 'auth_user__email', 'organization__name']
    list_filter = ['role', 'license_type', 'status', 'created_at']
    raw_id_fields = ['auth_user', 'organization']


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ['device_name', 'membership', 'device_type', 'last_seen_at', 'token_expires_at', 'created_at']
    search_fields = ['device_name', 'device_type', 'membership__email_used', 'membership__auth_user__email']
    list_filter = ['device_type', 'created_at', 'last_seen_at']
    raw_id_fields = ['membership']


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ['email', 'organization', 'role', 'license_type', 'status', 'created_at']
    search_fields = ['email', 'organization__name']
    list_filter = ['status', 'role', 'license_type', 'created_at']
    raw_id_fields = ['organization']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = [
        'app_name',
        'actor_email',
        'start_time',
        'end_time',
        'duration_seconds',
        'category',
        'data_quality_score',
        'created_at',
    ]
    search_fields = [
        'app_name',
        'window_title',
        'user__email',
        'membership__auth_user__email',
    ]
    list_filter = ['category', 'app_name', 'created_at']
    raw_id_fields = ['user', 'membership', 'device']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'data_quality_score', 'normalized_context']

    def actor_email(self, obj):
        if obj.user:
            return obj.user.email
        if obj.membership and obj.membership.auth_user:
            return obj.membership.auth_user.email
        return '-'
    actor_email.short_description = 'User Email'

    def duration_seconds(self, obj):
        return round(obj.duration, 2)
    duration_seconds.short_description = 'Duration (s)'


@admin.register(Gamification)
class GamificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'date', 'points', 'streak']
    search_fields = ['user__email']
    list_filter = ['date']
    raw_id_fields = ['user']
    date_hierarchy = 'date'


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ['device', 'event', 'created_at']
    search_fields = ['device__device_name', 'event']
    list_filter = ['event', 'created_at']
    raw_id_fields = ['device']


@admin.register(DataQualityMetrics)
class DataQualityMetricsAdmin(admin.ModelAdmin):
    list_display = [
        'organization',
        'date',
        'total_logs',
        'valid_logs',
        'avg_data_quality_score',
        'quality_status_display',
        'quality_degradation_flag',
        'high_violation_rate_flag',
    ]
    search_fields = ['organization__name']
    list_filter = ['date', 'quality_degradation_flag', 'high_violation_rate_flag']
    raw_id_fields = ['organization']

    def quality_status_display(self, obj):
        return obj.quality_status
    quality_status_display.short_description = 'Quality Status'


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['name', 'created_at']


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['created_at']


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ['role', 'permission']
    search_fields = ['role__name', 'permission__name']
    list_filter = ['role', 'permission']
    raw_id_fields = ['role', 'permission']


@admin.register(UserOrgRole)
class UserOrgRoleAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'role', 'state', 'invited_by', 'invited_at', 'accepted_at', 'created_at']
    search_fields = ['user__email', 'organization__name', 'role__name']
    list_filter = ['state', 'role', 'created_at', 'invited_at', 'accepted_at']
    raw_id_fields = ['user', 'organization', 'role', 'invited_by']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'parent_department', 'manager', 'created_at']
    search_fields = ['name', 'organization__name', 'manager__email']
    list_filter = ['organization', 'created_at']
    raw_id_fields = ['organization', 'parent_department', 'manager']


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'department', 'role_in_department', 'joined_at']
    search_fields = ['user__email', 'department__name', 'role_in_department']
    list_filter = ['joined_at']
    raw_id_fields = ['user', 'department']


@admin.register(OrganizationState)
class OrganizationStateAdmin(admin.ModelAdmin):
    list_display = ['organization', 'current_state', 'previous_state', 'state_changed_at', 'state_changed_by']
    search_fields = ['organization__name', 'current_state', 'previous_state']
    list_filter = ['current_state', 'previous_state', 'state_changed_at', 'created_at']
    raw_id_fields = ['organization', 'state_changed_by']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['actor_email', 'action', 'resource_type', 'resource_id', 'organization', 'created_at']
    search_fields = ['actor_email', 'resource_type', 'user_agent']
    list_filter = ['action', 'resource_type', 'organization', 'created_at']
    raw_id_fields = ['actor', 'organization']
    readonly_fields = ['created_at']


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'key_prefix', 'is_active', 'expires_at', 'last_used_at', 'created_at']
    search_fields = ['name', 'key_prefix', 'organization__name']
    list_filter = ['is_active', 'created_at', 'expires_at', 'last_used_at']
    raw_id_fields = ['organization', 'created_by']
    readonly_fields = ['key_prefix', 'key_hash', 'created_at', 'last_used_at']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient_email', 'notification_type', 'title', 'is_read', 'created_at']
    search_fields = ['recipient__email', 'title', 'message']
    list_filter = ['notification_type', 'is_read', 'created_at']
    raw_id_fields = ['recipient', 'organization', 'actor', 'related_user']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at', 'read_at']
    actions = ['mark_selected_as_read']
    fieldsets = (
        ('Recipient', {
            'fields': ('recipient', 'organization')
        }),
        ('Content', {
            'fields': ('notification_type', 'title', 'message', 'metadata')
        }),
        ('Related Users', {
            'fields': ('actor', 'related_user')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at', 'is_deleted', 'deleted_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def recipient_email(self, obj):
        return obj.recipient.email if obj.recipient else '-'
    recipient_email.short_description = 'Recipient Email'

    @admin.action(description='Mark selected notifications as read')
    def mark_selected_as_read(self, request, queryset):
        for notification in queryset.filter(is_read=False):
            notification.mark_as_read()
