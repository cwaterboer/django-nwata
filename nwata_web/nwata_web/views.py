from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from dashboard.forms import PersonalSignUpForm, TeamSignUpForm, LoginForm
from api.models import User, Device


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'home.html')


def signup_choice_view(request):
    """Let user choose between personal and team signup"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'signup_choice.html')


def personal_signup_view(request):
    """Signup for personal/individual workspace"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = PersonalSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Auto-login the user after signup
            login(request, user)
            messages.success(request, 'Welcome to Nwata! Your personal workspace is ready.')
            return redirect('onboarding')
    else:
        form = PersonalSignUpForm()
    
    return render(request, 'signup_personal.html', {'form': form})


def team_signup_view(request):
    """Signup for team organization"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = TeamSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Auto-login the user after signup
            login(request, user)
            messages.success(request, 'Welcome to Nwata! Your team workspace is created. Invite your team members next.')
            return redirect('onboarding')
    else:
        form = TeamSignUpForm()
    
    return render(request, 'signup_team.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data['identifier']
            password = form.cleaned_data['password']

            # Try direct username login first
            user = authenticate(request, username=identifier, password=password)

            if user is None:
                # Fallback: treat identifier as email
                from django.contrib.auth.models import User as AuthUser
                try:
                    auth_user = AuthUser.objects.get(email__iexact=identifier)
                    user = authenticate(request, username=auth_user.username, password=password)
                except AuthUser.DoesNotExist:
                    user = None

            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid credentials. Try your email or username.')
    else:
        form = LoginForm()
    
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required
def onboarding_view(request):
    # Check if user has any devices registered
    try:
        nwata_user = User.objects.get(email=request.user.email)
        # Check if user has any devices linked to their memberships
        has_devices = Device.objects.filter(
            membership__auth_user=request.user
        ).exists() if hasattr(request, 'membership') and request.membership else False
        org = nwata_user.org
        is_team_org = org.is_team() if org else False
    except User.DoesNotExist:
        has_devices = False
        org = None
        is_team_org = False
    
    context = {
        'user': request.user,
        'has_devices': has_devices,
        'org': org,
        'is_team_org': is_team_org,
        'org_setup_completed': is_team_org,  # Show as completed for now (can be more sophisticated later)
    }
    return render(request, 'onboarding.html', context)


@login_required
def device_setup_view(request):
    # Get user's organization info
    try:
        nwata_user = User.objects.select_related('org').get(email=request.user.email)
        org = nwata_user.org
    except User.DoesNotExist:
        org = None
    
    # Get user's devices from their current membership
    devices = []
    if hasattr(request, 'membership') and request.membership:
        devices = Device.objects.filter(
            membership=request.membership
        ).order_by('-last_seen_at')
    
    context = {
        'user': request.user,
        'org': org,
        'devices': devices,
        'api_url': request.build_absolute_uri('/').rstrip('/'),
    }
    return render(request, 'device_setup.html', context)


def about_view(request):
    return render(request, 'about.html')


def solutions_view(request):
    return render(request, 'solutions.html')


def use_cases_view(request):
    return render(request, 'use_cases.html')
