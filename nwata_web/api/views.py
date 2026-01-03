from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import ActivityLog, Gamification, User, Organization
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ActivityIngest(APIView):
    def post(self, request):
        data = request.data
        print(f"\n=== RAW ACTIVITY INGEST RECEIVED ===")
        print(f"Data type: {type(data)}")
        print(f"Data: {data}")
        print(f"Headers: {dict(request.headers)}")

        try:
            # Handle both single log and array of logs
            if isinstance(data, list):
                # Agent sends array of logs
                processed_count = 0
                for log_entry in data:
                    self._process_single_log(log_entry)
                    processed_count += 1
                print(f"Processed {processed_count} activity logs")
                return Response({"status": "success", "processed": processed_count}, status=status.HTTP_201_CREATED)
            else:
                # Single log entry
                activity = self._process_single_log(data)
                print(f"Created single ActivityLog: {activity.id}")
                return Response({"status": "success", "id": activity.id}, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"=== ERROR: {str(e)} ===")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def _process_single_log(self, log_data):
        # Create/get default organization and user for raw logs
        org, _ = Organization.objects.get_or_create(
            name="Default Org",
            defaults={"subdomain": "default"}
        )

        user, _ = User.objects.get_or_create(
            email="raw-logs@nwata.local",
            defaults={"org": org}
        )

        # Parse timestamps (agent sends ISO format)
        start_time = datetime.fromisoformat(log_data["start_time"].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(log_data["end_time"].replace('Z', '+00:00'))

        # Create activity log
        activity = ActivityLog.objects.create(
            user=user,
            app_name=log_data["app_name"],
            window_title=log_data.get("window_title", ""),
            start_time=start_time,
            end_time=end_time,
            category="Raw Log"  # Mark as raw log
        )

        print(f"✓ Created ActivityLog: {activity.id} - {activity.app_name} ({activity.window_title})")
        return activity
