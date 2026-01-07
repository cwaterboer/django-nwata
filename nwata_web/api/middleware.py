"""
Middleware for injecting user role and organization context into requests
"""
from .models import User as NwataUser, UserOrgRole


class OrganizationContextMiddleware:
    """
    Adds organization and role context to every request
    Sets request.organization and request.user_role
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Add organization context if user is authenticated
        request.organization = None
        request.user_role = None
        request.user_org_role = None
        
        if request.user.is_authenticated:
            try:
                nwata_user = NwataUser.objects.select_related('org').get(email=request.user.email)
                request.organization = nwata_user.org
                
                # Get user's role in organization
                try:
                    user_org_role = UserOrgRole.objects.select_related('role').get(
                        user=nwata_user,
                        organization=nwata_user.org,
                        state='active'
                    )
                    request.user_role = user_org_role.role
                    request.user_org_role = user_org_role
                except UserOrgRole.DoesNotExist:
                    pass
            except NwataUser.DoesNotExist:
                pass
        
        response = self.get_response(request)
        return response


class OrganizationStateCheckMiddleware:
    """
    Checks if organization is in active state
    Redirects to suspension page if organization is suspended
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip check for certain paths
        exempt_paths = ['/login/', '/logout/', '/signup/', '/admin/', '/api/']
        if any(request.path.startswith(path) for path in exempt_paths):
            return self.get_response(request)
        
        # Check organization state
        if request.user.is_authenticated and hasattr(request, 'organization') and request.organization:
            try:
                org_state = request.organization.state
                if org_state.current_state == 'suspended':
                    # TODO: Redirect to suspension notice page
                    from django.http import HttpResponse
                    return HttpResponse("Your organization is currently suspended. Please contact support.", status=403)
                elif org_state.current_state == 'archived':
                    from django.http import HttpResponse
                    return HttpResponse("This organization has been archived.", status=403)
            except Exception:
                pass  # No state object yet
        
        response = self.get_response(request)
        return response
