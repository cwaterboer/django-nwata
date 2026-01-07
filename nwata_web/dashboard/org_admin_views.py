"""
Views for organization administration and team management
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse

from api.models import (
    User as NwataUser, Organization, UserOrgRole, Role, 
    AuditLog, Department, Permission, RolePermission
)
from api.permissions import require_org_admin, require_org_member
from dashboard.org_admin_forms import (
    InviteUserForm, ChangeUserRoleForm, RemoveUserForm
)
from dashboard.forms import OrganizationSettingsForm


@login_required
@require_org_admin
@require_http_methods(["GET", "POST"])
def org_settings(request):
    """
    Main organization settings view with tabbed interface
    Handles: General settings, Members, Departments, Roles, Audit Log
    """
    org = request.organization
    
    if not org:
        messages.error(request, "You are not part of any organization.")
        return redirect('dashboard')
    
    # Get current NwataUser
    try:
        nwata_user = NwataUser.objects.get(email=request.user.email)
    except NwataUser.DoesNotExist:
        messages.error(request, "User profile not found.")
        return redirect('dashboard')
    
    # Get active tab from query parameter (default: general)
    active_tab = request.GET.get('tab', 'general')
    valid_tabs = ['general', 'members', 'departments', 'roles', 'audit']
    if active_tab not in valid_tabs:
        active_tab = 'general'
    
    # Context shared across all tabs
    context = {
        'org': org,
        'active_tab': active_tab,
        'is_team': org.is_team(),
    }
    
    # Tab: General Settings
    if active_tab == 'general' or request.method == 'POST':
        if request.method == 'POST' and 'general-settings' in request.POST:
            form = OrganizationSettingsForm(request.POST, instance=org)
            if form.is_valid():
                form.save()
                
                # Log audit entry
                AuditLog.objects.create(
                    actor=nwata_user,
                    actor_email=request.user.email,
                    action='org.settings_changed',
                    resource_type='organization',
                    resource_id=org.id,
                    organization=org,
                    changes_before={'name': org.name},
                    changes_after={'name': form.cleaned_data['name']},
                    ip_address=_get_client_ip(request)
                )
                
                messages.success(request, "Organization settings updated.")
                return redirect(reverse('org_settings') + '?tab=general')
        else:
            form = OrganizationSettingsForm(instance=org)
        
        context['form'] = form
    
    # Tab: Members
    if active_tab == 'members':
        active_users = UserOrgRole.objects.filter(
            organization=org,
            state='active'
        ).select_related('user', 'role').order_by('user__email')
        
        pending_users = UserOrgRole.objects.filter(
            organization=org,
            state__in=['pending', 'invited']
        ).select_related('user', 'role').order_by('created_at')
        
        # Handle invite form
        if request.method == 'POST' and 'invite_user' in request.POST:
            invite_form = InviteUserForm(request.POST, org=org)
            if invite_form.is_valid():
                email = invite_form.cleaned_data['email']
                role_name = invite_form.cleaned_data['role']
                
                existing = UserOrgRole.objects.filter(
                    organization=org,
                    user__email=email
                ).first()
                
                if existing:
                    messages.error(request, f"User {email} is already in this organization.")
                else:
                    try:
                        invited_user = NwataUser.objects.get(email=email)
                    except NwataUser.DoesNotExist:
                        invited_user = None
                    
                    role = Role.objects.get(name=role_name)
                    initial_state = 'invited' if invited_user else 'pending'
                    
                    user_org_role = UserOrgRole.objects.create(
                        user=invited_user if invited_user else None,
                        organization=org,
                        role=role,
                        state=initial_state,
                        invited_by=nwata_user,
                        invited_at=timezone.now()
                    )
                    
                    AuditLog.objects.create(
                        actor=nwata_user,
                        actor_email=request.user.email,
                        action='user.invited',
                        resource_type='user_org_role',
                        resource_id=user_org_role.id,
                        organization=org,
                        changes_after={
                            'email': email,
                            'role': role_name,
                            'organization': org.name,
                            'state': initial_state
                        },
                        ip_address=_get_client_ip(request)
                    )
                    
                    messages.success(request, f"Invitation sent to {email}.")
                    return redirect(reverse('org_settings') + '?tab=members')
        else:
            invite_form = InviteUserForm(org=org)
        
        context.update({
            'active_users': active_users,
            'pending_users': pending_users,
            'invite_form': invite_form,
        })
    
    # Tab: Departments
    if active_tab == 'departments':
        if not org.is_team():
            messages.warning(request, "Departments are only available for team organizations.")
        else:
            departments = Department.objects.filter(
                organization=org
            ).prefetch_related('userdepartment_set').order_by('name')
            context['departments'] = departments
    
    # Tab: Roles & Permissions
    if active_tab == 'roles':
        # Get all roles and their permissions
        roles = Role.objects.all().prefetch_related('role_permissions__permission').order_by('name')
        permissions = Permission.objects.all().order_by('name')
        
        # Build permission matrix
        role_permission_matrix = {}
        for role in roles:
            role_perms = RolePermission.objects.filter(role=role).values_list('permission__name', flat=True)
            role_permission_matrix[role.name] = set(role_perms)
        
        context.update({
            'roles': roles,
            'permissions': permissions,
            'role_permission_matrix': role_permission_matrix,
        })
    
    # Tab: Audit Log
    if active_tab == 'audit':
        audit_logs = AuditLog.objects.filter(
            organization=org
        ).select_related('actor').order_by('-created_at')[:50]
        context['audit_logs'] = audit_logs
    
    return render(request, 'dashboard/org_settings.html', context)


@login_required
@require_org_admin
@require_http_methods(["GET", "POST"])
def manage_users(request):
    """
    View to manage users in organization (for backward compatibility)
    Redirects to org_settings tab=members
    """
    return redirect(reverse('org_settings') + '?tab=members')


# Legacy view functions (kept for backward compatibility with direct URL access)
    
    if not org:
        messages.error(request, "You are not part of any organization.")
        return redirect('dashboard')
    
    # Get all active users in organization
    active_users = UserOrgRole.objects.filter(
        organization=org,
        state='active'
    ).select_related('user', 'role').order_by('user__email')
    
    # Get pending/invited users
    pending_users = UserOrgRole.objects.filter(
        organization=org,
        state__in=['pending', 'invited']
    ).select_related('user', 'role').order_by('created_at')
    
    # Handle invitation
    if request.method == 'POST' and 'invite_user' in request.POST:
        form = InviteUserForm(request.POST, org=org)
        if form.is_valid():
            email = form.cleaned_data['email']
            role_name = form.cleaned_data['role']
            
            # Check if user already exists in org
            existing = UserOrgRole.objects.filter(
                organization=org,
                user__email=email
            ).first()
            
            if existing:
                messages.error(request, f"User {email} is already in this organization.")
            else:
                # Try to find existing Nwata user
                try:
                    nwata_user = NwataUser.objects.get(email=email)
                except NwataUser.DoesNotExist:
                    # Create pending user
                    nwata_user = None
                
                role = Role.objects.get(name=role_name)
                
                # Create UserOrgRole (invited state if user exists, pending if not)
                initial_state = 'invited' if nwata_user else 'pending'
                
                user_org_role = UserOrgRole.objects.create(
                    user=nwata_user if nwata_user else None,
                    organization=org,
                    role=role,
                    state=initial_state,
                    invited_by=nwata_user,
                    invited_at=timezone.now()
                )
                
                # Log audit entry
                AuditLog.objects.create(
                    actor=nwata_user,
                    actor_email=request.user.email,
                    action='user.invited',
                    resource_type='user_org_role',
                    resource_id=user_org_role.id,
                    organization=org,
                    changes_after={
                        'email': email,
                        'role': role_name,
                        'organization': org.name,
                        'state': initial_state
                    },
                    ip_address=_get_client_ip(request)
                )
                
                # TODO: Send invitation email
                messages.success(
                    request, 
                    f"Invitation sent to {email} with {role_name} role."
                )
                return redirect('manage_users')
        
        context = {
            'org': org,
            'active_users': active_users,
            'pending_users': pending_users,
            'invite_form': form,
        }
        return render(request, 'dashboard/manage_users.html', context)
    
    # Initial GET request
    invite_form = InviteUserForm(org=org)
    
    context = {
        'org': org,
        'active_users': active_users,
        'pending_users': pending_users,
        'invite_form': invite_form,
    }
    
    return render(request, 'dashboard/manage_users.html', context)


@login_required
@require_org_admin
@require_http_methods(["GET", "POST"])
def change_user_role(request, user_id):
    """
    Change user's role in organization
    """
    org = request.organization
    
    # Get current NwataUser
    try:
        nwata_user = NwataUser.objects.get(email=request.user.email)
    except NwataUser.DoesNotExist:
        messages.error(request, "User profile not found.")
        return redirect('dashboard')
    
    # Get user role
    user_org_role = get_object_or_404(
        UserOrgRole,
        id=user_id,
        organization=org,
        state='active'
    )
    
    # Can't change owner role
    if user_org_role.role.name == 'owner':
        messages.error(request, "Cannot change owner's role.")
        return redirect('manage_users')
    
    # Can't change if they're changing owner
    if nwata_user == user_org_role.user:
        messages.error(request, "Cannot change your own role.")
        return redirect('manage_users')
    
    if request.method == 'POST':
        form = ChangeUserRoleForm(request.POST)
        if form.is_valid():
            new_role_name = form.cleaned_data['role']
            new_role = Role.objects.get(name=new_role_name)
            
            old_role = user_org_role.role
            user_org_role.role = new_role
            user_org_role.save()
            
            # Log audit entry
            AuditLog.objects.create(
                actor=nwata_user,
                actor_email=request.user.email,
                action='user.role_changed',
                resource_type='user_org_role',
                resource_id=user_org_role.id,
                organization=org,
                changes_before={'role': old_role.name},
                changes_after={'role': new_role.name},
                ip_address=_get_client_ip(request)
            )
            
            messages.success(
                request,
                f"Changed {user_org_role.user.email}'s role to {new_role.name}."
            )
            return redirect('manage_users')
    else:
        form = ChangeUserRoleForm(initial={'role': user_org_role.role.name})
    
    context = {
        'org': org,
        'user_org_role': user_org_role,
        'form': form,
    }
    
    return render(request, 'dashboard/change_user_role.html', context)


@login_required
@require_org_admin
@require_http_methods(["GET", "POST"])
def remove_user(request, user_id):
    """
    Remove user from organization
    """
    org = request.organization
    
    # Get current NwataUser
    try:
        nwata_user = NwataUser.objects.get(email=request.user.email)
    except NwataUser.DoesNotExist:
        messages.error(request, "User profile not found.")
        return redirect('dashboard')
    
    # Get user role
    user_org_role = get_object_or_404(
        UserOrgRole,
        id=user_id,
        organization=org
    )
    
    # Can't remove owner
    if user_org_role.role.name == 'owner':
        messages.error(request, "Cannot remove owner from organization.")
        return redirect('manage_users')
    
    # Can't remove yourself
    if nwata_user == user_org_role.user:
        messages.error(request, "Cannot remove yourself from organization.")
        return redirect('manage_users')
    
    if request.method == 'POST':
        form = RemoveUserForm(request.POST)
        if form.is_valid():
            removed_user_email = user_org_role.user.email
            
            # Log audit entry before deletion
            AuditLog.objects.create(
                actor=nwata_user,
                actor_email=request.user.email,
                action='user.removed',
                resource_type='user_org_role',
                resource_id=user_org_role.id,
                organization=org,
                changes_before={
                    'user': removed_user_email,
                    'role': user_org_role.role.name,
                    'state': user_org_role.state
                },
                ip_address=_get_client_ip(request)
            )
            
            user_org_role.delete()
            
            messages.success(
                request,
                f"Removed {removed_user_email} from organization."
            )
            return redirect('manage_users')
    else:
        form = RemoveUserForm()
    
    context = {
        'org': org,
        'user_org_role': user_org_role,
        'form': form,
    }
    
    return render(request, 'dashboard/remove_user.html', context)


@login_required
@require_org_member()
@require_http_methods(["GET"])
def view_audit_log(request):
    """
    View organization audit log
    Only available to members with view_audit_logs permission
    """
    org = request.organization
    
    # Check permission
    if 'view_audit_logs' not in request.user_permissions:
        return HttpResponseForbidden("You don't have permission to view audit logs.")
    
    # Get audit logs for organization
    audit_logs = AuditLog.objects.filter(
        Q(changes_after__organization=org.id) |
        Q(actor__organization=org)
    ).select_related('actor').order_by('-timestamp')[:100]
    
    # Pagination can be added here
    context = {
        'org': org,
        'audit_logs': audit_logs,
    }
    
    return render(request, 'dashboard/audit_log.html', context)


@login_required
@require_org_admin
@require_http_methods(["GET", "POST"])
def manage_departments(request):
    """
    Manage departments within organization
    """
    org = request.organization
    
    if not org.is_team():
        messages.error(request, "Departments are only available for team organizations.")
        return redirect('dashboard')
    
    # Get all departments
    departments = Department.objects.filter(
        organization=org
    ).prefetch_related('userdepartment_set').order_by('name')
    
    # TODO: Handle department creation/editing
    
    context = {
        'org': org,
        'departments': departments,
    }
    
    return render(request, 'dashboard/manage_departments.html', context)


def _get_client_ip(request):
    """
    Get client IP address from request
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
