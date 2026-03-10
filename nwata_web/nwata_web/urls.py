"""
URL configuration for nwata_web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import (
    home, signup_choice_view, personal_signup_view, team_signup_view, 
    login_view, logout_view, onboarding_view, device_setup_view,
    about_view, solutions_view, use_cases_view
)

urlpatterns = [
    path("", home, name='home'),
    path('signup/', signup_choice_view, name='signup'),
    path('signup/personal/', personal_signup_view, name='signup_personal'),
    path('signup/team/', team_signup_view, name='signup_team'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('onboarding/', onboarding_view, name='onboarding'),
    path('device-setup/', device_setup_view, name='device_setup'),
    path('about/', about_view, name='about'),
    path('solutions/', solutions_view, name='solutions'),
    path('use-cases/', use_cases_view, name='use_cases'),
    path("admin/", admin.site.urls),
    path('api/', include('api.urls')),
    path('dashboard/', include('dashboard.urls')),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
