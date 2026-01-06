from django import forms
from django.contrib.auth.models import User as AuthUser
from django.contrib.auth.forms import PasswordChangeForm
from api.models import User, Organization


class ProfileUpdateForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    username = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    organization_name = forms.CharField(max_length=255, required=True)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['username'].initial = self.user.username
            self.fields['email'].initial = self.user.email
            
            try:
                nwata_user = User.objects.get(email=self.user.email)
                if nwata_user.org:
                    self.fields['organization_name'].initial = nwata_user.org.name
            except User.DoesNotExist:
                pass

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if self.user and email != self.user.email:
            # Check if email is already taken by another user
            if AuthUser.objects.filter(email=email).exclude(id=self.user.id).exists():
                raise forms.ValidationError('This email is already in use.')
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if self.user and username != self.user.username:
            # Check if username is already taken
            if AuthUser.objects.filter(username=username).exclude(id=self.user.id).exists():
                raise forms.ValidationError('This username is already taken.')
        return username

    def save(self):
        if not self.user:
            return None
            
        # Update Django auth user
        self.user.first_name = self.cleaned_data['first_name']
        self.user.last_name = self.cleaned_data['last_name']
        self.user.username = self.cleaned_data['username']
        self.user.email = self.cleaned_data['email']
        self.user.save()

        # Update organization
        try:
            nwata_user = User.objects.get(email=self.user.email)
            if nwata_user.org:
                nwata_user.org.name = self.cleaned_data['organization_name']
                nwata_user.org.save()
        except User.DoesNotExist:
            pass

        return self.user
