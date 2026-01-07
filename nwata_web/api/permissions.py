"""
Permission checking decorators and utilities for RBAC
"""
from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib import messages
from .models import UserOrgRole, RolePermission, Permission


def get_user_role_in_org(user, organization):
    """Get user's role in an organization"""
    try:
        user_org_role = UserOrgRole.objects.select_related('role').get(
            user__email=user.email,
            organization=organization,
            state='active'
        )
        return user_org_role.role
    except UserOrgRole.DoesNotExist:
        return None


def get_user_permissions_in_org(user, organization):
    """Get all permissions for a user in an organization"""
    role = get_user_role_in_org(user, organization)
    if not role:
        return []
    
    # Get all permissions for this role
    role_perms = RolePermission.objects.filter(role=role).select_related('permission')
    return [rp.permission.name for rp in role_perms]


def has_permission(user, organization, permission_name):
    """Check if user has a specific permission in organization"""
    user_permissions = get_user_permissions_in_org(user, organization)
    return permission_name in user_permissions


def has_role(user, organization, role_name):
    """Check if user has a specific role in organization"""
    role = get_user_role_in_org(user, organization)
    return role and role.name == role_name


def is_org_owner(user, organization):
    """Check if user is owner of organization"""
    return has_role(user, organization, 'owner')


def is_org_admin(user, organization):
    """Check if user is owner or admin of organization"""
    role = get_user_role_in_org(user, organization)
    return role and role.name in ['owner', 'admin']


# Decorators for view protection

def require_permission(permission_name):
    """
    Decorator to require a specific permission
    Usage: @require_permission('invite_users')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Get user's organization from context
            org = getattr(request, 'organization', None)
            if not org:
                # Try to get from user's nwata user
                from .models import User as NwataUser
                try:
                    nwata_user = NwataUser.objects.get(email=request.user.email)
                    org = nwata_user.org
                except NwataUser.DoesNotExist:
                    messages.error(request, "You don't have access to any organization.")
                    return redirect('home')
            
            if not has_permission(request.user, org, permission_name):
                messages.error(request, f"You don't have permission to {permission_name.replace('_', ' ')}.")
                return HttpResponseForbidden("Permission denied")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_role(role_name):
    """
    Decorator to require a specific role
    Usage: @require_role('admin')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Get user's organization
            from .models import User as NwataUser
            try:
                nwata_user = NwataUser.objects.get(email=request.user.email)
                org = nwata_user.org
            except NwataUser.DoesNotExist:
                messages.error(request, "You don't have access to any organization.")
                return redirect('home')
            
            if not has_role(request.user, org, role_name):
                messages.error(request, f"You must be an organization {role_name} to access this.")
                return HttpResponseForbidden("Permission denied")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_org_admin(view_func):
    """
    Decorator to require owner or admin role
    Usage: @require_org_admin or @require_org_admin()
    """
    # Support both @require_org_admin and @require_org_admin()
    if callable(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Get user's organization from middleware
            org = getattr(request, 'organization', None)
            if not org:
                messages.error(request, "You don't have access to any organization.")
                return redirect('home')
            
            if not is_org_admin(request.user, org):
                messages.error(request, "You must be an organization owner or admin to access this.")
                return HttpResponseForbidden("Permission denied")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    else:
        # Called with @require_org_admin()
        def decorator(view_func):
            @wraps(view_func)
            def wrapper(request, *args, **kwargs):
                if not request.user.is_authenticated:
                    return redirect('login')
                
                # Get user's organization from middleware
                org = getattr(request, 'organization', None)
                if not org:
                    messages.error(request, "You don't have access to any organization.")
                    return redirect('home')
                
                if not is_org_admin(request.user, org):
                    messages.error(request, "You must be an organization owner or admin to access this.")
                    return HttpResponseForbidden("Permission denied")
                
                return view_func(request, *args, **kwargs)
            return wrapper
        return decorator


def require_org_member():
    """
    Decorator to require active membership in organization
    Usage: @require_org_member()
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Get user's organization from middleware
            org = getattr(request, 'organization', None)
            if not org:
                messages.error(request, "You don't have access to any organization.")
                return redirect('home')
            
            # Check if user is active member
            try:
                user_org_role = UserOrgRole.objects.get(
                    user__email=request.user.email,
                    organization=org,
                    state='active'
                )
            except UserOrgRole.DoesNotExist:
                messages.error(request, "You are not an active member of this organization.")
                return HttpResponseForbidden("Permission denied")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_org_owner(view_func):
    """
    Decorator to require owner role only
    Usage: @require_org_owner
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Get user's organization
        from .models import User as NwataUser
        try:
            nwata_user = NwataUser.objects.get(email=request.user.email)
            org = nwata_user.org
        except NwataUser.DoesNotExist:
            messages.error(request, "You don't have access to any organization.")
            return redirect('home')
        
        if not is_org_owner(request.user, org):
            messages.error(request, "You must be the organization owner to access this.")
            return HttpResponseForbidden("Permission denied")
        
        return view_func(request, *args, **kwargs)
    return wrapper


# Context processor for templates

def get_user_context(user):
    """
    Get user's role and permissions for template context
    Returns dict with role, permissions, is_admin, is_owner
    """
    from .models import User as NwataUser
    
    context = {
        'user_role': None,
        'user_permissions': [],
        'is_org_admin': False,
        'is_org_owner': False,
        'organization': None,
    }
    
    if not user.is_authenticated:
        return context
    
    try:
        nwata_user = NwataUser.objects.get(email=user.email)
        org = nwata_user.org
        
        context['organization'] = org
        context['user_role'] = get_user_role_in_org(user, org)
        context['user_permissions'] = get_user_permissions_in_org(user, org)
        context['is_org_admin'] = is_org_admin(user, org)
        context['is_org_owner'] = is_org_owner(user, org)
    except NwataUser.DoesNotExist:
        pass
    
    return context
