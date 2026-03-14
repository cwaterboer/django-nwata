from django.urls import path
from . import views
from .org_admin_views import (
    manage_users, change_user_role, remove_user, 
    view_audit_log, manage_departments, org_settings
)

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/app-comparison/', views.get_app_comparison_data, name='app_comparison_data'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/change-password/', views.change_password_view, name='change_password'),
    
    # Organization administration (tabbed interface)
    path('org/settings/', org_settings, name='org_settings'),
    
    # Legacy organization routes (kept for backward compatibility)
    path('org/users/', manage_users, name='manage_users'),
    path('org/users/<int:user_id>/role/', change_user_role, name='change_user_role'),
    path('org/users/<int:user_id>/remove/', remove_user, name='remove_user'),
    path('org/audit-log/', view_audit_log, name='view_audit_log'),
    path('org/departments/', manage_departments, name='manage_departments'),
]