from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import ActivityLog, Gamification, User, Organization
import logging
from datetime import datetime
from django.utils import timezone

logger = logging.getLogger(__name__)


class ActivityIngest(APIView):
    """
    API endpoint for ingesting activity logs from local agents.
    Currently allows unauthenticated access for MVP - should be secured in production.
    """
    permission_classes = [AllowAny]  # TODO: Add authentication for production

    def post(self, request):
        data = request.data
        logger.info(f"Activity ingest received - Type: {type(data)}, Count: {len(data) if isinstance(data, list) else 1}")

        try:
            # Validate input
            if not data:
                return Response(
                    {"error": "No data provided"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Handle both single log and array of logs
            if isinstance(data, list):
                processed_count = 0
                errors = []
                
                for idx, log_entry in enumerate(data):
                    try:
                        self._validate_log_entry(log_entry)
                        self._process_single_log(log_entry)
                        processed_count += 1
                    except ValueError as e:
                        errors.append(f"Entry {idx}: {str(e)}")
                        logger.warning(f"Validation error in entry {idx}: {str(e)}")
                
                response_data = {
                    "status": "success",
                    "processed": processed_count,
                    "total": len(data)
                }
                
                if errors:
                    response_data["errors"] = errors
                    
                logger.info(f"Processed {processed_count}/{len(data)} activity logs")
                return Response(response_data, status=status.HTTP_201_CREATED)
            else:
                # Single log entry
                self._validate_log_entry(data)
                activity = self._process_single_log(data)
                logger.info(f"Created single ActivityLog: {activity.id}")
                return Response(
                    {"status": "success", "id": activity.id},
                    status=status.HTTP_201_CREATED
                )

        except ValueError as e:
            logger.error(f"Validation error: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _validate_log_entry(self, log_data):
        """Validate required fields in log entry"""
        required_fields = ['app_name', 'start_time', 'end_time']
        missing_fields = [field for field in required_fields if field not in log_data]
        
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
        
        # Validate timestamps
        try:
            start = datetime.fromisoformat(log_data["start_time"].replace('Z', '+00:00'))
            end = datetime.fromisoformat(log_data["end_time"].replace('Z', '+00:00'))
            
            if end < start:
                raise ValueError("end_time must be after start_time")
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid timestamp format: {str(e)}")

    def _process_single_log(self, log_data):
        """Process and create a single activity log entry"""
        # Get or create default organization and user for raw logs
        org, created = Organization.objects.get_or_create(
            subdomain="default",
            defaults={"name": "Default Organization"}
        )
        if created:
            logger.info("Created default organization")

        user, created = User.objects.get_or_create(
            email="raw-logs@nwata.local",
            defaults={"org": org}
        )
        if created:
            logger.info("Created default user for raw logs")

        # Parse timestamps with timezone awareness
        start_time = datetime.fromisoformat(log_data["start_time"].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(log_data["end_time"].replace('Z', '+00:00'))
        
        # Ensure timezone-aware datetimes
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
        if timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time)

        # Create activity log
        activity = ActivityLog.objects.create(
            user=user,
            app_name=log_data["app_name"],
            window_title=log_data.get("window_title", ""),
            start_time=start_time,
            end_time=end_time,
            category=log_data.get("category", "Raw Log")
        )

        logger.debug(
            f"Created ActivityLog {activity.id}: {activity.app_name} "
            f"({activity.duration:.1f}s)"
        )
        return activity
