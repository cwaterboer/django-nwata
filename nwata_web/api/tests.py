from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from .models import Organization, User, ActivityLog, Gamification, Device
from datetime import datetime, timedelta


class OrganizationModelTest(TestCase):
    def test_organization_creation(self):
        org = Organization.objects.create(name="Test Org", subdomain="test")
        self.assertEqual(str(org), "Test Org")
        self.assertEqual(org.subdomain, "test")


class UserModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", subdomain="test")

    def test_user_creation(self):
        user = User.objects.create(email="test@example.com", org=self.org)
        self.assertEqual(str(user), "test@example.com (Test Org)")


class ActivityLogModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", subdomain="test")
        self.user = User.objects.create(email="test@example.com", org=self.org)

    def test_activity_log_creation(self):
        start = timezone.now()
        end = start + timedelta(minutes=5)
        
        activity = ActivityLog.objects.create(
            user=self.user,
            app_name="Chrome",
            window_title="Test Page",
            start_time=start,
            end_time=end,
            category="Browsing"
        )
        
        self.assertEqual(activity.duration, 300.0)  # 5 minutes = 300 seconds
        self.assertEqual(activity.app_name, "Chrome")


class ActivityIngestAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/activity/'
        self.org = Organization.objects.create(name="Test Org", subdomain="test")
        self.user = User.objects.create(email="test@example.com", org=self.org)
        self.device = Device.objects.create(
            user=self.user,
            name="Test Agent",
            token="test-token",
            token_expires_at=timezone.now() + timedelta(days=1)
        )
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Bearer {self.device.token}"}

    def test_single_log_ingest(self):
        start = timezone.now()
        end = start + timedelta(minutes=10)
        
        data = {
            "app_name": "VS Code",
            "window_title": "test.py",
            "start_time": start.isoformat(),
            "end_time": end.isoformat()
        }
        
        response = self.client.post(self.url, data, format='json', **self.auth_headers)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'success')
        self.assertTrue(ActivityLog.objects.filter(app_name="VS Code").exists())

    def test_bulk_log_ingest(self):
        start = timezone.now()
        
        data = [
            {
                "app_name": "Chrome",
                "window_title": "Page 1",
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(minutes=5)).isoformat()
            },
            {
                "app_name": "Slack",
                "window_title": "Chat",
                "start_time": (start + timedelta(minutes=5)).isoformat(),
                "end_time": (start + timedelta(minutes=10)).isoformat()
            }
        ]
        
        response = self.client.post(self.url, data, format='json', **self.auth_headers)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['processed'], 2)
        self.assertEqual(ActivityLog.objects.count(), 2)

    def test_missing_required_fields(self):
        data = {"app_name": "Chrome"}  # Missing start_time and end_time
        
        response = self.client.post(self.url, data, format='json', **self.auth_headers)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_invalid_timestamps(self):
        start = timezone.now()
        end = start - timedelta(minutes=5)  # End before start
        
        data = {
            "app_name": "Chrome",
            "start_time": start.isoformat(),
            "end_time": end.isoformat()
        }
        
        response = self.client.post(self.url, data, format='json', **self.auth_headers)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GamificationModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org", subdomain="test")
        self.user = User.objects.create(email="test@example.com", org=self.org)

    def test_gamification_unique_constraint(self):
        date = timezone.now().date()
        
        Gamification.objects.create(user=self.user, points=100, streak=5, date=date)
        
        # Attempting to create another record for same user and date should fail
        with self.assertRaises(Exception):
            Gamification.objects.create(user=self.user, points=200, streak=6, date=date)
