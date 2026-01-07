from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from dashboard.forms import SignUpForm, LoginForm
from api.models import User, Device


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'home.html')


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Auto-login the user after signup
            login(request, user)
            messages.success(request, 'Welcome to Nwata! Let\'s get you started.')
            return redirect('onboarding')
    else:
        form = SignUpForm()
    
    return render(request, 'signup.html', {'form': form})


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
        has_devices = Device.objects.filter(user=nwata_user).exists()
    except User.DoesNotExist:
        has_devices = False
    
    context = {
        'user': request.user,
        'has_devices': has_devices,
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
    
    # Get user's devices
    devices = Device.objects.filter(user__email=request.user.email).order_by('-last_seen')
    
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
