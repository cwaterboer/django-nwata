"""
Middleware for injecting user role and organization context into requests
"""
from .models import (
    User as NwataUser,
    UserOrgRole,
    Organization,
    OrganizationState,
    Role,
)


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
            nwata_user = None
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
                nwata_user = self._provision_user_context(request.user)
                if nwata_user:
                    request.organization = nwata_user.org
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
        
        response = self.get_response(request)
        return response

    def _provision_user_context(self, auth_user):
        """
        Fallback to provision a personal organization + Nwata user mapping
        for authenticated users (e.g., staff/superusers created via createsuperuser)
        so the sidebar/org routes have organization context.
        """
        try:
            email = auth_user.email or f"{auth_user.username}@example.com"
            display_name = auth_user.first_name or auth_user.username or "User"

            subdomain = Organization.generate_personal_subdomain(email)
            org_defaults = {
                'name': f"{display_name}'s Workspace",
                'organization_type': 'personal',
            }
            organization, _ = Organization.objects.get_or_create(
                subdomain=subdomain,
                defaults=org_defaults,
            )

            # Ensure org state exists
            OrganizationState.objects.get_or_create(
                organization=organization,
                defaults={'current_state': 'active'},
            )

            nwata_user, _ = NwataUser.objects.get_or_create(
                email=email,
                defaults={'org': organization},
            )

            # If the user existed without org, attach it
            if nwata_user.org_id is None:
                nwata_user.org = organization
                nwata_user.save(update_fields=['org'])

            owner_role, _ = Role.objects.get_or_create(
                name='owner',
                defaults={'description': 'Owner role with full access'},
            )

            UserOrgRole.objects.get_or_create(
                user=nwata_user,
                organization=organization,
                defaults={
                    'role': owner_role,
                    'state': 'active',
                },
            )

            return nwata_user
        except Exception:
            return None


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
