"""
Locust load testing for Nwata notification system.

Run with:
    locust -f tests/locustfile.py --host=http://localhost:8000
    
Or for web UI:
    locust -f tests/locustfile.py --host=http://localhost:8000 --web
"""

from locust import HttpUser, task, between, TaskSet, events
from locust.exception import StopUser
import random
import logging
import os
import time

logger = logging.getLogger(__name__)


# ==========================================
# TEST DATA
# ==========================================

class NotificationTasks(TaskSet):
    """Notification system load tests"""

    def _auto_signup_personal_user(self):
        """Create a unique personal account when explicit credentials are not provided."""
        signup_page = self.client.get("/signup/personal/")
        csrf_token = self.client.cookies.get("csrftoken")
        if signup_page.status_code != 200 or not csrf_token:
            raise StopUser("Unable to fetch CSRF token from /signup/personal/")

        unique_id = int(time.time() * 1000) + random.randint(1000, 9999)
        email = f"locust_{unique_id}@example.com"
        password = os.getenv("NWATA_LOADTEST_DEFAULT_PASS", "LocustTestPass123!")

        signup_response = self.client.post(
            "/signup/personal/",
            data={
                "first_name": "Load",
                "last_name": "Tester",
                "email": email,
                "password1": password,
                "password2": password,
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"Referer": f"{self.client.base_url}/signup/personal/"},
            allow_redirects=False,
        )

        if signup_response.status_code not in (302, 303):
            raise StopUser(f"Auto-signup failed with status {signup_response.status_code}")

        session_id = self.client.cookies.get("sessionid")
        if not session_id:
            raise StopUser("Auto-signup did not produce a sessionid cookie")

        logger.info("Auto-signup succeeded for %s", email)
        return email, password

    def _login(self, username, password):
        """Perform form login to obtain session and csrf cookies."""
        login_page = self.client.get("/login/")
        csrf_token = self.client.cookies.get("csrftoken")
        if login_page.status_code != 200 or not csrf_token:
            raise StopUser("Unable to fetch CSRF token from /login/")

        login_response = self.client.post(
            "/login/",
            data={
                "identifier": username,
                "password": password,
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"Referer": f"{self.client.base_url}/login/"},
            allow_redirects=False,
        )

        if login_response.status_code not in (302, 303):
            raise StopUser(f"Login failed with status {login_response.status_code}")

        session_id = self.client.cookies.get("sessionid")
        if not session_id:
            raise StopUser("Login did not create sessionid cookie")
    
    def on_start(self):
        """Authenticate session user before running API tasks."""
        username = os.getenv("NWATA_LOADTEST_USER")
        password = os.getenv("NWATA_LOADTEST_PASS")
        auto_signup = os.getenv("NWATA_AUTO_SIGNUP", "false").lower() == "true"

        if username and password:
            self._login(username, password)
        elif auto_signup:
            username, password = self._auto_signup_personal_user()
            logger.info("Using auto-generated account for load user: %s", username)
        else:
            logger.error(
                "Load user stopped: missing NWATA_LOADTEST_USER/NWATA_LOADTEST_PASS and NWATA_AUTO_SIGNUP is disabled."
            )
            raise StopUser(
                "Missing credentials. Set NWATA_LOADTEST_USER/NWATA_LOADTEST_PASS or enable NWATA_AUTO_SIGNUP=true."
            )

        self.headers = {
            "X-CSRFToken": self.client.cookies.get("csrftoken", ""),
            "Content-Type": "application/json"
        }
    
    @task(10)
    def get_unread_count(self):
        """Simulate checking unread notification count"""
        with self.client.get(
            "/api/notifications/unread-count/",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.failure("Unauthorized")
            else:
                response.failure(f"Got code {response.status_code}")
    
    @task(8)
    def get_notifications_list(self):
        """Fetch notifications list with pagination"""
        limit = random.choice([10, 20, 50])
        unread_only = random.choice([True, False])
        
        with self.client.get(
            f"/api/notifications/?limit={limit}&unread_only={unread_only}",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got code {response.status_code}")
    
    @task(5)
    def get_single_notification(self):
        """Fetch a single notification"""
        notification_id = random.randint(1, 1000)
        
        with self.client.get(
            f"/api/notifications/{notification_id}/",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Got code {response.status_code}")
    
    @task(4)
    def mark_notification_as_read(self):
        """Mark a notification as read"""
        notification_id = random.randint(1, 1000)
        
        with self.client.patch(
            f"/api/notifications/{notification_id}/",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Got code {response.status_code}")
    
    @task(3)
    def delete_notification(self):
        """Soft delete a notification"""
        notification_id = random.randint(1, 1000)
        
        with self.client.delete(
            f"/api/notifications/{notification_id}/",
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code in [204, 404]:
                response.success()
            else:
                response.failure(f"Got code {response.status_code}")
    
    @task(2)
    def bulk_mark_as_read(self):
        """Mark multiple notifications as read"""
        notification_ids = [random.randint(1, 1000) for _ in range(random.randint(3, 10))]
        
        with self.client.post(
            "/api/notifications/mark-as-read/",
            headers=self.headers,
            json={"notification_ids": notification_ids},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got code {response.status_code}")


# ==========================================
# LOAD TEST USERS
# ==========================================

class NotificationUser(HttpUser):
    """User that performs notification tasks"""
    tasks = [NotificationTasks]
    wait_time = between(3, 7)  # Wait 3-7 seconds between requests


class BurstNotificationUser(HttpUser):
    """User that rapidly performs notification checks (simulates dashboard monitoring)"""
    tasks = [NotificationTasks]
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests (dashboard polling)


# ==========================================
# EVENT HANDLERS FOR REPORTING
# ==========================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts"""
    logger.info("=== Notification Load Test Started ===")
    logger.info(f"Target: {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops"""
    logger.info("=== Notification Load Test Completed ===")
    logger.info(f"Total requests: {environment.stats.total.num_requests}")
    logger.info(f"Total failures: {environment.stats.total.num_failures}")
    logger.info(f"Average response time: {environment.stats.total.avg_response_time:.2f}ms")
    min_response_time = environment.stats.total.min_response_time
    max_response_time = environment.stats.total.max_response_time

    if min_response_time is None or max_response_time is None:
        logger.info("Min response time: n/a (no requests recorded)")
        logger.info("Max response time: n/a (no requests recorded)")
    else:
        logger.info(f"Min response time: {min_response_time:.2f}ms")
        logger.info(f"Max response time: {max_response_time:.2f}ms")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Called for each request (for detailed logging)"""
    if exception:
        logger.error(f"Request failed: {request_type} {name} - {exception}")


# ==========================================
# TEST SCENARIOS
# ==========================================

class StressTestScenario:
    """
    Stress test configuration for 1000+ concurrent users.
    
    Run with:
        locust -f tests/locustfile.py --host=http://localhost:8000 \\
               -u 1000 -r 50 -t 5m
    
    Where:
    - u 1000 = 1000 concurrent users
    - r 50   = spawn 50 new users per second
    - t 5m   = run for 5 minutes
    """
    pass


class SpikeTest:
    """
    Spike test to see how system handles sudden traffic jumps.
    
    Run with:
        locust -f tests/locustfile.py --host=http://localhost:8000 \\
               -u 100 -r 10 -t 1m  # Build up to 100 users
        # Wait a minute, then increase:
        # Change to: -u 500 -r 100  # Spike to 500 users
    """
    pass


class EnduranceTest:
    """
    Endurance test over extended period (hours).
    
    Run with:
        locust -f tests/locustfile.py --host=http://localhost:8000 \\
               -u 200 -r 20 -t 4h
    """
    pass
