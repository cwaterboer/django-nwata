"""
Forms for organization administration
"""
from django import forms
from api.models import User as NwataUser, Organization, UserOrgRole, Role


class InviteUserForm(forms.Form):
    """Form to invite a new user to organization"""
    email = forms.EmailField(label="User Email", help_text="Email of the user to invite")
    role = forms.ChoiceField(
        label="Role",
        choices=[
            ('member', 'Member'),
            ('admin', 'Admin'),
        ],
        help_text="Choose the user's role in the organization"
    )
    
    def __init__(self, *args, org=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.org = org
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        if not email:
            raise forms.ValidationError('Email is required.')
        
        if email == '@example.com' or '@example.com' in email:
            raise forms.ValidationError('Invalid email address.')
        
        return email
    
    def clean_role(self):
        role_name = self.cleaned_data.get('role')
        
        try:
            Role.objects.get(name=role_name)
        except Role.DoesNotExist:
            raise forms.ValidationError('Invalid role selected.')
        
        return role_name


class ChangeUserRoleForm(forms.Form):
    """Form to change user's role"""
    role = forms.ChoiceField(
        label="New Role",
        choices=[
            ('member', 'Member'),
            ('admin', 'Admin'),
        ]
    )


class RemoveUserForm(forms.Form):
    """Confirmation form for removing user"""
    confirm = forms.BooleanField(
        label="Yes, I want to remove this user from the organization",
        required=True
    )
