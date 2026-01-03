from django.shortcuts import render
from django.db.models import Count, Sum, Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncHour, ExtractHour
from api.models import ActivityLog, Gamification, User, Organization
from datetime import datetime, timedelta
from collections import defaultdict

def dashboard(request):
    now = datetime.now()
    today = now.date()
    week_start = today - timedelta(days=today.weekday())

    # Get organization (default to first org if exists)
    org = Organization.objects.first()

    # Active users today (users with activity today)
    active_users_today = User.objects.filter(
        activitylog__created_at__date=today
    ).distinct().count()

    # Get recent activity logs (last 24 hours) with duration calculation
    recent_activities = ActivityLog.objects.select_related('user', 'user__org').annotate(
        duration_minutes=ExpressionWrapper(
            F('end_time') - F('start_time'),
            output_field=DurationField()
        )
    ).order_by('-created_at')[:100]

    # Calculate durations for recent activities
    for activity in recent_activities:
        activity.duration_display = round(activity.duration_minutes.total_seconds() / 60, 1)

    # Today's activities with proper duration calculation
    today_activities = ActivityLog.objects.filter(
        created_at__date=today
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

    # App usage stats with proper duration calculation
    app_stats = []
    for app_name in ActivityLog.objects.values_list('app_name', flat=True).distinct():
        app_activities = ActivityLog.objects.filter(
            app_name=app_name,
            created_at__date=today
        ).annotate(
            duration_minutes=ExpressionWrapper(
                F('end_time') - F('start_time'),
                output_field=DurationField()
            )
        )

        total_duration = sum(a.duration_minutes.total_seconds() / 60 for a in app_activities)
        app_stats.append({
            'app_name': app_name,
            'count': app_activities.count(),
            'total_duration': round(total_duration, 1),
            'avg_duration': round(total_duration / app_activities.count(), 1) if app_activities.count() > 0 else 0
        })

    app_stats.sort(key=lambda x: x['total_duration'], reverse=True)

    # Session tracking - group activities within 5 minutes of each other
    sessions = []
    current_session = []
    session_threshold = timedelta(minutes=5)

    sorted_activities = ActivityLog.objects.filter(
        created_at__date=today
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

    # User stats
    user_stats = User.objects.annotate(
        activity_count=Count('activitylog'),
        total_points=Sum('gamification__points'),
        avg_streak=Avg('gamification__streak')
    ).select_related('org')

    # Activity categories (if any)
    category_stats = ActivityLog.objects.values('category').annotate(
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

    # Weekly streak (count of days with activity this week)
    week_activity_days = ActivityLog.objects.filter(
        created_at__date__gte=week_start,
        created_at__date__lte=today
    ).values('created_at__date').distinct().count()
    weekly_streak = week_activity_days

    context = {
        'org': org,
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
        'total_users': User.objects.count(),
        'total_activities': ActivityLog.objects.count(),
        'last_updated': now,
    }

    return render(request, 'dashboard/dashboard.html', context)
