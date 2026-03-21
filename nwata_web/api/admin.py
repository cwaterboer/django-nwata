from django.contrib import admin
from .models import Organization, User, ActivityLog, Gamification, Notification


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'subdomain', 'created_at']
    search_fields = ['name', 'subdomain']
    list_filter = ['created_at']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'org', 'created_at']
    search_fields = ['email']
    list_filter = ['org', 'created_at']
    raw_id_fields = ['org']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['app_name', 'user', 'start_time', 'end_time', 'category', 'created_at']
    search_fields = ['app_name', 'window_title', 'user__email']
    list_filter = ['category', 'app_name', 'created_at']
    raw_id_fields = ['user']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at']


@admin.register(Gamification)
class GamificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'date', 'points', 'streak']
    search_fields = ['user__email']
    list_filter = ['date']
    raw_id_fields = ['user']
    date_hierarchy = 'date'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient_email', 'notification_type', 'title', 'is_read', 'created_at']
    search_fields = ['recipient__email', 'title', 'message']
    list_filter = ['notification_type', 'is_read', 'created_at']
    raw_id_fields = ['recipient', 'organization', 'actor', 'related_user']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at', 'read_at']
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
        return obj.recipient.email
    recipient_email.short_description = 'Recipient Email'
