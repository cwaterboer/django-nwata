"""
Celery configuration for nwata_web project.
"""

import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nwata_web.settings')

app = Celery('nwata_web')

# Load configuration from Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered Django apps
app.autodiscover_tasks()

# Celery Beat schedule for periodic tasks
app.conf.beat_schedule = {
    'cleanup-expired-invitations': {
        'task': 'api.tasks.cleanup_expired_invitations',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'cleanup-old-notifications': {
        'task': 'api.tasks.cleanup_old_notifications',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
    },
}

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f'Request: {self.request!r}')
