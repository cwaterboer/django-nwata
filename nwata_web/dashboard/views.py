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

def get_period_dates(period, reference_date):
    """Get date ranges for current and previous periods"""
    if period == 'week':
        # Week-on-week: current week vs previous week
        week_start = reference_date - timedelta(days=reference_date.weekday())
        current_start = week_start
        current_end = reference_date
        previous_start = week_start - timedelta(days=7)
        previous_end = week_start - timedelta(days=1)
    elif period == 'month':
        # Month-on-month: current month vs previous month
        current_start = reference_date.replace(day=1)
        if reference_date.month == 12:
            previous_start = reference_date.replace(year=reference_date.year, month=11, day=1)
            previous_end = reference_date.replace(year=reference_date.year, month=11, day=30)
        else:
            previous_start = reference_date.replace(month=reference_date.month-1, day=1)
            previous_end = reference_date.replace(day=1) - timedelta(days=1)
        current_end = reference_date
    elif period == 'quarter':
        # Quarter-on-quarter: current quarter vs previous quarter
        quarter = ((reference_date.month - 1) // 3) + 1
        if quarter == 1:
            current_start = reference_date.replace(month=1, day=1)
            previous_start = reference_date.replace(year=reference_date.year-1, month=10, day=1)
            previous_end = reference_date.replace(year=reference_date.year-1, month=12, day=31)
        else:
            current_start = reference_date.replace(month=((quarter-1)*3)+1, day=1)
            previous_start = reference_date.replace(month=((quarter-2)*3)+1, day=1)
            previous_end = current_start - timedelta(days=1)
        current_end = reference_date
    elif period == 'year':
        # Year-on-year: current year vs previous year
        current_start = reference_date.replace(month=1, day=1)
        current_end = reference_date
        previous_start = reference_date.replace(year=reference_date.year-1, month=1, day=1)
        previous_end = reference_date.replace(year=reference_date.year-1, month=12, day=31)
    else:  # 'today' or default
        current_start = current_end = reference_date
        previous_start = previous_end = reference_date - timedelta(days=1)

    return {
        'current': {'start': current_start, 'end': current_end},
        'previous': {'start': previous_start, 'end': previous_end}
    }

def get_app_usage_stats(org_filter, date_range):
    """Get app usage statistics for a given date range"""
    app_activities = ActivityLog.objects.filter(
        created_at__date__gte=date_range['start'],
        created_at__date__lte=date_range['end'],
        **org_filter
    ).exclude(
        app_name__isnull=True
    ).exclude(
        app_name=''
    ).values('app_name').annotate(
        activity_count=Count('id'),
        total_duration_seconds=Sum(
            ExpressionWrapper(
                F('end_time') - F('start_time'),
                output_field=DurationField()
            )
        )
    ).order_by('-total_duration_seconds')

    app_stats = []
    for app_data in app_activities:
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

    return app_stats

def create_app_comparison(current_stats, previous_stats, period):
    """Create comparison data between current and previous periods"""
    if not previous_stats:
        return current_stats  # Return current stats if no comparison

    # Create lookup dicts for easy comparison
    current_dict = {app['app_name']: app for app in current_stats}
    previous_dict = {app['app_name']: app for app in previous_stats}

    comparison = []
    all_apps = set(current_dict.keys()) | set(previous_dict.keys())

    for app_name in all_apps:
        current = current_dict.get(app_name, {'count': 0, 'total_duration': 0, 'avg_duration': 0})
        previous = previous_dict.get(app_name, {'count': 0, 'total_duration': 0, 'avg_duration': 0})

        # Calculate changes
        count_change = current['count'] - previous['count']
        duration_change = current['total_duration'] - previous['total_duration']
        avg_change = current['avg_duration'] - previous['avg_duration']

        # Calculate percentages (avoid division by zero)
        count_change_pct = (count_change / previous['count'] * 100) if previous['count'] > 0 else (100 if current['count'] > 0 else 0)
        duration_change_pct = (duration_change / previous['total_duration'] * 100) if previous['total_duration'] > 0 else (100 if current['total_duration'] > 0 else 0)

        comparison.append({
            'app_name': app_name,
            'current': current,
            'previous': previous,
            'count_change': count_change,
            'count_change_pct': round(count_change_pct, 1),
            'duration_change': round(duration_change, 1),
            'duration_change_pct': round(duration_change_pct, 1),
            'avg_change': round(avg_change, 1),
            'trend': 'up' if duration_change > 0 else 'down' if duration_change < 0 else 'same'
        })

    # Sort by current period duration (descending)
    comparison.sort(key=lambda x: x['current']['total_duration'], reverse=True)
    return comparison

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
    # Support for time period comparisons
    period = request.GET.get('period', 'today')
    period_dates = get_period_dates(period, today)

    app_stats = get_app_usage_stats(org_filter, period_dates['current'])
    app_stats_previous = get_app_usage_stats(org_filter, period_dates['previous']) if period != 'today' else []

    # Create comparison data
    app_comparison = create_app_comparison(app_stats, app_stats_previous, period)

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
        'app_stats': app_stats[:10],  # Top 10 apps (legacy - for other tabs)
        'app_comparison': app_comparison[:10],  # Top 10 apps with comparison data
        'current_period': period,
        'period_dates': period_dates,
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
