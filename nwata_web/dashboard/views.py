from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Count, Sum, Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncHour, ExtractHour
from api.models import ActivityLog, Gamification, User, Organization
from datetime import datetime, timedelta
from collections import defaultdict
from .profile_forms import ProfileUpdateForm

@login_required
def dashboard(request):
    now = datetime.now()
    today = now.date()
    week_start = today - timedelta(days=today.weekday())

    # Get current user's organization
    try:
        nwata_user = User.objects.get(email=request.user.email)
        org = nwata_user.org
    except User.DoesNotExist:
        # If user doesn't have a Nwata User record, they can't see any data
        org = None

    # Filter all queries by organization
    org_filter = {'user__org': org} if org else {'user__org__isnull': True}

    # Active users today (users with activity today in this org)
    active_users_today = User.objects.filter(
        org=org,
        activity_logs__created_at__date=today
    ).distinct().count() if org else 0

    # Get recent activity logs (last 24 hours) with duration calculation - ONLY for this org
    recent_activities = ActivityLog.objects.filter(**org_filter).select_related('user', 'user__org').annotate(
        duration_minutes=ExpressionWrapper(
            F('end_time') - F('start_time'),
            output_field=DurationField()
        )
    ).order_by('-created_at')[:100]

    # Calculate durations for recent activities
    for activity in recent_activities:
        activity.duration_display = round(activity.duration_minutes.total_seconds() / 60, 1)
        # Parse context if available for display
        if activity.context:
            activity.typing_count = activity.context.get('typing_count', 0)
            activity.scroll_count = activity.context.get('scroll_count', 0)
            activity.shortcut_count = activity.context.get('shortcut_count', 0)
            activity.idle_seconds = round(activity.context.get('total_idle_ms', 0) / 1000, 1)
            activity.typing_rate = activity.context.get('typing_rate_per_min', 0)
        else:
            activity.typing_count = 0
            activity.scroll_count = 0
            activity.shortcut_count = 0
            activity.idle_seconds = 0
            activity.typing_rate = 0

    # Today's activities with proper duration calculation - filtered by org
    today_activities = ActivityLog.objects.filter(
        created_at__date=today,
        **org_filter
    ).annotate(
        duration_minutes=ExpressionWrapper(
            F('end_time') - F('start_time'),
            output_field=DurationField()
        )
    )

    # Calculate total time spent today
    total_time_today = sum(
        activity.duration_minutes.total_seconds() / 60
        for activity in today_activities
    )

    # Hourly activity breakdown for today
    hourly_stats = defaultdict(lambda: {'count': 0, 'duration': 0})
    for activity in today_activities:
        hour = activity.start_time.hour
        hourly_stats[hour]['count'] += 1
        hourly_stats[hour]['duration'] += activity.duration_minutes.total_seconds() / 60

    # Convert to sorted list for template
    hourly_breakdown = [
        {'hour': hour, 'count': hourly_stats[hour]['count'], 'duration': round(hourly_stats[hour]['duration'], 1)}
        for hour in sorted(hourly_stats.keys())
    ]

    # App usage stats with proper duration calculation - filtered by org
    # Use aggregation to avoid duplicates and improve performance
    app_stats = []
    today_app_activities = ActivityLog.objects.filter(
        created_at__date=today,
        **org_filter
    ).exclude(
        app_name__isnull=True  # Exclude None app names
    ).exclude(
        app_name=''  # Exclude empty strings
    ).values('app_name').annotate(
        activity_count=Count('id'),
        total_duration_seconds=Sum(
            ExpressionWrapper(
                F('end_time') - F('start_time'),
                output_field=DurationField()
            )
        )
    ).order_by('-total_duration_seconds')

    for app_data in today_app_activities:
        app_name = app_data['app_name']
        count = app_data['activity_count']
        total_seconds = app_data['total_duration_seconds']
        
        if total_seconds:
            total_minutes = total_seconds.total_seconds() / 60
        else:
            total_minutes = 0
            
        app_stats.append({
            'app_name': app_name,
            'count': count,
            'total_duration': round(total_minutes, 1),
            'avg_duration': round(total_minutes / count, 1) if count > 0 else 0
        })

    # Session tracking - group activities within 5 minutes of each other
    sessions = []
    current_session = []
    session_threshold = timedelta(minutes=5)

    sorted_activities = ActivityLog.objects.filter(
        created_at__date=today,
        **org_filter
    ).order_by('start_time')

    for activity in sorted_activities:
        if not current_session:
            current_session.append(activity)
        else:
            last_activity = current_session[-1]
            if activity.start_time - last_activity.end_time <= session_threshold:
                current_session.append(activity)
            else:
                if current_session:
                    sessions.append(current_session)
                current_session = [activity]

    if current_session:
        sessions.append(current_session)

    # Calculate session stats
    session_stats = []
    for session in sessions[-10:]:  # Last 10 sessions
        session_start = min(a.start_time for a in session)
        session_end = max(a.end_time for a in session)
        duration = (session_end - session_start).total_seconds() / 60
        app_count = len(set(a.app_name for a in session))

        session_stats.append({
            'start_time': session_start,
            'end_time': session_end,
            'duration': round(duration, 1),
            'activity_count': len(session),
            'app_count': app_count,
            'apps': list(set(a.app_name for a in session))[:3]  # Top 3 apps
        })

    # User stats - filtered by org
    user_stats = User.objects.filter(org=org).annotate(
        activity_count=Count('activity_logs'),
        total_points=Sum('gamification_records__points'),
        avg_streak=Avg('gamification_records__streak')
    ).select_related('org') if org else []

    # Activity categories (if any) - filtered by org
    category_stats = ActivityLog.objects.filter(**org_filter).values('category').annotate(
        count=Count('id'),
        total_duration=Sum(
            ExpressionWrapper(
                F('end_time') - F('start_time'),
                output_field=DurationField()
            )
        )
    ).order_by('-count')

    # MVP KPIs for Summary Cards
    # Total focus hours (today)
    total_focus_hours = round(total_time_today / 60, 1)  # Convert minutes to hours

    # Average focus % (placeholder - targeting 8 hours/day)
    target_hours = 8
    avg_focus_percent = min(round((total_focus_hours / target_hours) * 100, 1), 100)

    # Weekly streak (count of days with activity this week) - filtered by org
    week_activity_days = ActivityLog.objects.filter(
        created_at__date__gte=week_start,
        created_at__date__lte=today,
        **org_filter
    ).values('created_at__date').distinct().count()
    weekly_streak = week_activity_days

    context = {
        'org': org,
        'current_user': request.user,
        'active_users_today': active_users_today,
        'total_focus_hours': total_focus_hours,
        'avg_focus_percent': avg_focus_percent,
        'weekly_streak': weekly_streak,
        'recent_activities': recent_activities[:20],  # Show last 20
        'total_time_today': round(total_time_today, 1),
        'activity_count_today': today_activities.count(),
        'hourly_breakdown': hourly_breakdown,
        'app_stats': app_stats[:10],  # Top 10 apps
        'session_stats': session_stats,
        'category_stats': category_stats,
        'user_stats': user_stats,
        'total_users': User.objects.filter(org=org).count() if org else 0,
        'total_activities': ActivityLog.objects.filter(**org_filter).count(),
        'last_updated': now,
    }

    return render(request, 'dashboard/dashboard.html', context)


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(user=request.user)
    
    # Get organization info
    try:
        nwata_user = User.objects.get(email=request.user.email)
        org = nwata_user.org
    except User.DoesNotExist:
        org = None
    
    context = {
        'form': form,
        'org': org,
        'current_user': request.user,
    }
    return render(request, 'dashboard/profile.html', context)


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep user logged in
            messages.success(request, 'Password changed successfully!')
            return redirect('profile')
    else:
        form = PasswordChangeForm(request.user)
    
    context = {
        'form': form,
        'current_user': request.user,
    }
    return render(request, 'dashboard/change_password.html', context)
