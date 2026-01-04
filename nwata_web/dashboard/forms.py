from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User as AuthUser
from api.models import User, Organization


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text='Required. Enter a valid email address.')
    organization_name = forms.CharField(max_length=255, required=True, help_text='Your organization name.')
    
    class Meta:
        model = AuthUser
        fields = ('username', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email

    def save(self, commit=True):
        # Create Django auth user
        auth_user = super().save(commit=False)
        auth_user.email = self.cleaned_data['email']
        
        if commit:
            auth_user.save()
            
            # Create organization
            org_name = self.cleaned_data['organization_name']
            subdomain = org_name.lower().replace(' ', '-')[:50]
            
            # Ensure unique subdomain
            base_subdomain = subdomain
            counter = 1
            while Organization.objects.filter(subdomain=subdomain).exists():
                subdomain = f"{base_subdomain}-{counter}"
                counter += 1
            
            org = Organization.objects.create(
                name=org_name,
                subdomain=subdomain
            )
            
            # Create Nwata user linked to organization
            User.objects.create(
                email=self.cleaned_data['email'],
                org=org
            )
        
        return auth_user


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
