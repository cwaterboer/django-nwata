from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User as AuthUser
from api.models import User, Organization, UserOrgRole, Role, OrganizationState


class PersonalSignUpForm(UserCreationForm):
    """Signup form for personal/individual workspace"""
    first_name = forms.CharField(max_length=150, required=True, help_text='Your first name.')
    last_name = forms.CharField(max_length=150, required=False, help_text='Optional.')
    email = forms.EmailField(required=True, help_text='Required. Enter a valid email address.')
    
    class Meta:
        model = AuthUser
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email

    def save(self, commit=True):
        # Create Django auth user
        auth_user = super().save(commit=False)
        auth_user.username = self.cleaned_data.get('email')
        auth_user.first_name = self.cleaned_data.get('first_name', '')
        auth_user.last_name = self.cleaned_data.get('last_name', '')
        auth_user.email = self.cleaned_data['email']
        
        if commit:
            auth_user.save()
            
            # Create personal organization
            email = self.cleaned_data['email']
            first_name = self.cleaned_data.get('first_name', 'User')
            subdomain = Organization.generate_personal_subdomain(email)
            
            org = Organization.objects.create(
                name=f"{first_name}'s Workspace",
                subdomain=subdomain,
                organization_type='personal'
            )
            
            # Create organization state
            OrganizationState.objects.create(
                organization=org,
                current_state='active'
            )
            
            # Create Nwata user linked to organization
            nwata_user = User.objects.create(
                email=email,
                org=org
            )
            
            # Create UserOrgRole with owner role
            owner_role = Role.objects.get(name='owner')
            UserOrgRole.objects.create(
                user=nwata_user,
                organization=org,
                role=owner_role,
                state='active',
                invited_at=auth_user.date_joined,
                accepted_at=auth_user.date_joined,
            )
        
        return auth_user


class TeamSignUpForm(UserCreationForm):
    """Signup form for team organization"""
    first_name = forms.CharField(max_length=150, required=True, help_text='Your first name.')
    last_name = forms.CharField(max_length=150, required=False, help_text='Optional.')
    email = forms.EmailField(required=True, help_text='Required. Enter a valid email address.')
    organization_name = forms.CharField(max_length=255, required=True, help_text='Your team/organization name.')
    organization_slug = forms.CharField(
        max_length=50, 
        required=True, 
        help_text='URL-friendly name (lowercase, hyphens ok).',
        label='Organization URL'
    )
    
    class Meta:
        model = AuthUser
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email
    
    def clean_organization_slug(self):
        slug = self.cleaned_data.get('organization_slug', '').lower().strip()
        
        # Validate format
        if not slug:
            raise forms.ValidationError('Organization URL is required.')
        
        if len(slug) < 3:
            raise forms.ValidationError('Organization URL must be at least 3 characters.')
        
        if not slug.replace('-', '').isalnum():
            raise forms.ValidationError('Organization URL can only contain letters, numbers, and hyphens.')
        
        # Check reserved words
        reserved = ['admin', 'api', 'dashboard', 'login', 'signup', 'logout', 'onboarding', 'personal']
        if slug in reserved:
            raise forms.ValidationError(f'"{slug}" is reserved. Please choose another.')
        
        # Check uniqueness
        if Organization.objects.filter(subdomain=slug).exists():
            raise forms.ValidationError('This organization URL is already taken.')
        
        return slug

    def save(self, commit=True):
        # Create Django auth user
        auth_user = super().save(commit=False)
        auth_user.username = self.cleaned_data.get('email')
        auth_user.first_name = self.cleaned_data.get('first_name', '')
        auth_user.last_name = self.cleaned_data.get('last_name', '')
        auth_user.email = self.cleaned_data['email']
        
        if commit:
            auth_user.save()
            
            # Create team organization
            org_name = self.cleaned_data['organization_name']
            org_slug = self.cleaned_data['organization_slug']
            
            org = Organization.objects.create(
                name=org_name,
                subdomain=org_slug,
                organization_type='team'
            )
            
            # Create organization state
            OrganizationState.objects.create(
                organization=org,
                current_state='active'
            )
            
            # Create Nwata user linked to organization
            nwata_user = User.objects.create(
                email=self.cleaned_data['email'],
                org=org
            )
            
            # Create UserOrgRole with owner role
            owner_role = Role.objects.get(name='owner')
            UserOrgRole.objects.create(
                user=nwata_user,
                organization=org,
                role=owner_role,
                state='active',
                invited_at=auth_user.date_joined,
                accepted_at=auth_user.date_joined,
            )
        
        return auth_user


class LoginForm(forms.Form):
    identifier = forms.CharField(max_length=150, label="Email or Username")
    password = forms.CharField(widget=forms.PasswordInput)

class OrganizationSettingsForm(forms.ModelForm):
    """Form for updating organization settings"""
    
    class Meta:
        model = Organization
        fields = ['name', 'subdomain']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-gray-800 text-white border border-gray-700 rounded px-3 py-2 focus:outline-none focus:border-orange-500',
                'placeholder': 'Organization name',
            }),
            'subdomain': forms.TextInput(attrs={
                'class': 'w-full bg-gray-800 text-white border border-gray-700 rounded px-3 py-2 focus:outline-none focus:border-orange-500',
                'placeholder': 'org-url',
                'readonly': 'readonly',
            }),
        }
        labels = {
            'name': 'Organization Name',
            'subdomain': 'Organization URL',
        }
    
    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError('Organization name is required.')
        if len(name) > 255:
            raise forms.ValidationError('Organization name must be 255 characters or less.')
        return name