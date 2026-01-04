from django.db import models

class Organization(models.Model):
    name = models.CharField(max_length=255)
    subdomain = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['subdomain']),
        ]

    def __str__(self):
        return self.name

class User(models.Model):
    email = models.EmailField(unique=True)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='users')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['org', 'created_at']),
        ]

    def __str__(self):
        return f"{self.email} ({self.org.name})"

class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    app_name = models.CharField(max_length=255, db_index=True)
    window_title = models.CharField(max_length=500, null=True, blank=True)
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    category = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['app_name', 'created_at']),
            models.Index(fields=['start_time', 'end_time']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.app_name} - {self.user.email} ({self.start_time})"

    @property
    def duration(self):
        """Calculate duration in seconds"""
        return (self.end_time - self.start_time).total_seconds()

class Gamification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamification_records')
    points = models.IntegerField(default=0)
    streak = models.IntegerField(default=0)
    date = models.DateField(db_index=True)

    class Meta:
        unique_together = [['user', 'date']]
        indexes = [
            models.Index(fields=['user', 'date']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.user.email} - {self.date} (Points: {self.points}, Streak: {self.streak})"


class Device(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices')
    name = models.CharField(max_length=255, default='Agent')
    token = models.CharField(max_length=512, unique=True)
    token_expires_at = models.DateTimeField()
    last_seen = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['user', 'last_seen']),
        ]

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class DeviceEvent(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='events')
    event = models.CharField(max_length=50)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['device', 'event']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.device} - {self.event} @ {self.created_at}"
