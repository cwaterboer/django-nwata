"""
Locust load testing for Nwata notification system.

Run with:
    locust -f tests/locustfile.py --host=http://localhost:8000
    
Or for web UI:
    locust -f tests/locustfile.py --host=http://localhost:8000 --web
"""

from locust import HttpUser, task, between, TaskSet, events
import random
import logging

logger = logging.getLogger(__name__)


# ==========================================
# TEST DATA
# ==========================================

class NotificationTasks(TaskSet):
    """Notification system load tests"""
    
    def on_start(self):
        """Setup for each user"""
        # In production, authenticate with actual token
        self.user_id = random.randint(1, 100)
        self.auth_token = "test-token-" + str(self.user_id)
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
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
                response.fail("Unauthorized")
            else:
                response.fail(f"Got code {response.status_code}")
    
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
                response.fail(f"Got code {response.status_code}")
    
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
                response.fail(f"Got code {response.status_code}")
    
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
                response.fail(f"Got code {response.status_code}")
    
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
                response.fail(f"Got code {response.status_code}")
    
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
                response.fail(f"Got code {response.status_code}")


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
    logger.info(f"Min response time: {environment.stats.total.min_response_time:.2f}ms")
    logger.info(f"Max response time: {environment.stats.total.max_response_time:.2f}ms")


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
