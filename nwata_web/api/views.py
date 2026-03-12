from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.http import FileResponse
from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta
import secrets
import logging
import os
from .models import ActivityLog, Gamification, User, Organization, Device, DeviceEvent, DataQualityMetrics, validate_context_data

logger = logging.getLogger(__name__)
UserModel = get_user_model()
TOKEN_TTL_DAYS = 30


def _parse_iso(ts: str) -> datetime:
    """Parse ISO timestamp to aware datetime."""
    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def _issue_device_token(device):
    device.token = secrets.token_urlsafe(48)
    device.token_expires_at = timezone.now() + timedelta(days=TOKEN_TTL_DAYS)
    device.save(update_fields=["token", "token_expires_at", "last_seen"])
    return device.token, device.token_expires_at


class DeviceAuthMixin:
    def _get_device_from_request(self, request, require_active=True):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            raise PermissionError("Authorization header missing or invalid")

        token = auth_header.split(' ', 1)[1].strip()
        try:
            device = Device.objects.select_related('membership__organization').get(token=token)
        except Device.DoesNotExist:
            raise PermissionError("Invalid device token")

        if require_active and device.token_expires_at and device.token_expires_at < timezone.now():
            raise PermissionError("Device token expired")

        device.last_seen_at = timezone.now()
        device.save(update_fields=["last_seen_at"])
        return device


class DeviceRegister(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        device_name = request.data.get('device_name', 'Agent')

        if not email or not password:
            return Response({"error": "email and password are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Support login by email or username
        auth_user = None
        if UserModel.objects.filter(email=email).exists():
            username = UserModel.objects.get(email=email).username
            auth_user = authenticate(request, username=username, password=password)
        if auth_user is None:
            auth_user = authenticate(request, username=email, password=password)

        if auth_user is None:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        # Get or create user's active membership
        membership, created = None, False
        org = None
        
        try:
            # Try to get existing active membership
            membership = Membership.objects.select_related('organization').get(
                auth_user=auth_user,
                status='active'
            )
            org = membership.organization
        except Membership.DoesNotExist:
            # No active membership - check legacy User model
            try:
                nwata_user = User.objects.select_related('org').get(email=auth_user.email)
                org = nwata_user.org
            except User.DoesNotExist:
                # Create default organization if user has no org
                org, _ = Organization.objects.get_or_create(
                    subdomain="default",
                    defaults={"name": "Default Organization"}
                )
            
            # Create a Membership for this auth_user on their organization
            if org:
                membership, created = Membership.objects.get_or_create(
                    auth_user=auth_user,
                    organization=org,
                    defaults={
                        'role': 'member',
                        'email_used': auth_user.email,
                        'status': 'active'
                    }
                )
                # If membership existed but was not active, activate it
                if not created and membership.status != 'active':
                    membership.status = 'active'
                    membership.save(update_fields=['status'])

        if not org or not membership:
            return Response(
                {"error": "Failed to initialize user organization"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        device = Device.objects.create(
            membership=membership,
            device_name=device_name,
            token_expires_at=timezone.now(),  # will be set in _issue_device_token
        )

        token, expires_at = _issue_device_token(device)

        return Response({
            "token": token,
            "token_expires_at": expires_at.isoformat(),
            "user": {
                "email": auth_user.email,
                "id": auth_user.id,
            },
            "organization": {
                "id": org.id,
                "subdomain": org.subdomain,
                "name": org.name,
            }
        }, status=status.HTTP_201_CREATED)


class DeviceAuth(DeviceAuthMixin, APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            device = self._get_device_from_request(request, require_active=False)
        except PermissionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        # Refresh token/expiry
        token, expires_at = _issue_device_token(device)

        org_data = {}
        if device.membership:
            org_data = {
                "id": device.membership.organization.id,
                "subdomain": device.membership.organization.subdomain,
                "name": device.membership.organization.name,
            }

        return Response({
            "token": token,
            "token_expires_at": expires_at.isoformat(),
            "user": {
                "email": device.membership.auth_user.email if device.membership else None,
                "id": device.membership.auth_user.id if device.membership else None,
            },
            "organization": org_data
        }, status=status.HTTP_200_OK)


class DeviceLifecycle(DeviceAuthMixin, APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            device = self._get_device_from_request(request)
        except PermissionError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        # Validate request.data is a dict, not a list
        if not isinstance(request.data, dict):
            return Response({
                "error": "Invalid request format. Expected object with 'event', 'payload', and optional 'timestamp' fields."
            }, status=status.HTTP_400_BAD_REQUEST)

        event = request.data.get('event')
        payload = request.data.get('payload', {})
        timestamp = request.data.get('timestamp')

        if not event:
            return Response({"error": "event is required"}, status=status.HTTP_400_BAD_REQUEST)

        if timestamp:
            payload['reported_at'] = timestamp

        DeviceEvent.objects.create(device=device, event=event, payload=payload)
        return Response({"status": "ok"}, status=status.HTTP_201_CREATED)


class ActivityIngest(DeviceAuthMixin, APIView):
    """
    API endpoint for ingesting activity logs from local agents.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        logger.info(f"Activity ingest received - Type: {type(data)}, Count: {len(data) if isinstance(data, list) else 1}")

        try:
            device = self._get_device_from_request(request)
            if not device.membership:
                raise ValueError("Device is not associated with a membership")
            org = device.membership.organization
            if org is None:
                raise ValueError("Device membership is not associated with an organization")
        except (PermissionError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

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
                        self._process_single_log(log_entry, device.membership)
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
                activity = self._process_single_log(data, device.membership)
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
            start = _parse_iso(log_data["start_time"])
            end = _parse_iso(log_data["end_time"])
            
            if end < start:
                raise ValueError("end_time must be after start_time")
                
            # Check for reasonable duration
            duration = (end - start).total_seconds()
            if duration > 28800:  # 8 hours
                raise ValueError("Activity duration exceeds 8 hours")
                
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid timestamp format: {str(e)}")
        
        # Validate context data
        context = log_data.get("context")
        if context is not None:
            is_valid, errors, warnings = validate_context_data(context)
            if not is_valid:
                raise ValueError(f"Context validation failed: {', '.join(errors)}")
            
            # Store validation results for logging
            log_data['_context_warnings'] = warnings

    def _process_single_log(self, log_data, membership):
        """Process and create a single activity log entry for a specific membership"""
        start_time = _parse_iso(log_data["start_time"])
        end_time = _parse_iso(log_data["end_time"])

        activity = ActivityLog.objects.create(
            membership=membership,
            app_name=log_data["app_name"],
            window_title=log_data.get("window_title", ""),
            start_time=start_time,
            end_time=end_time,
            category=log_data.get("category"),
            context=log_data.get("context"),  # Context signals from agent
        )
        
        # Log warnings if any
        warnings = log_data.get('_context_warnings', [])
        if warnings:
            logger.warning(f"Context warnings for log {activity.id}: {warnings}")
        
        logger.debug(
            f"Created ActivityLog {activity.id}: {activity.app_name} "
            f"({activity.duration:.1f}s, quality: {activity.data_quality_score:.2f})"
        )
        return activity


class DownloadAgent(APIView):
    """
    API endpoint for downloading the Nwata tracking agent.
    Redirects to Google Cloud Storage where the agent zip is hosted.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # Redirect to cloud-hosted agent zip
        agent_url = 'https://storage.cloud.google.com/gcf-v2-uploads-606096666000.us-central1.cloudfunctions.appspot.com/nwata-agent.zip'
        logger.info(f"Agent download redirected to: {agent_url} from {request.META.get('REMOTE_ADDR')}")
        return Response(
            {"download_url": agent_url},
            status=status.HTTP_302_FOUND
        )


# ========================================
# DATA QUALITY MONITORING ENDPOINTS
# ========================================

class DataQualityMetricsView(DeviceAuthMixin, APIView):
    """
    Get data quality metrics for a specific date or date range.
    Returns aggregated metrics for ML readiness assessment.
    """

    def get(self, request):
        """
        Query parameters:
        - date: YYYY-MM-DD (required) - Get metrics for specific date
        - org_id: Organization ID (optional, defaults to device's org)
        """
        try:
            device = self._get_device_from_request(request)
            org = device.membership.organization if device.membership else None
            if not org:
                return Response(
                    {"error": "Device not associated with an organization"},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            org_id = request.query_params.get('org_id', org.id)
            
            # Verify user has access to this org
            if str(org_id) != str(org.id):
                return Response(
                    {"error": "Unauthorized access to organization"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            date_str = request.query_params.get('date')
            if not date_str:
                return Response(
                    {"error": "date parameter (YYYY-MM-DD) is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Parse date
            try:
                query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get metrics for date
            metrics = DataQualityMetrics.objects.filter(
                date=query_date,
                organization__id=org_id
            ).first()
            
            if not metrics:
                # Return empty metrics if none exist yet
                return Response({
                    "date": query_date.isoformat(),
                    "organization_id": org_id,
                    "message": "No metrics available for this date",
                    "total_logs": 0,
                    "valid_logs": 0,
                    "quality_status": "UNKNOWN"
                })
            
            return Response({
                "date": metrics.date.isoformat(),
                "organization_id": metrics.organization.id,
                "organization_name": metrics.organization.name,
                "total_logs": metrics.total_logs,
                "valid_logs": metrics.valid_logs,
                "schema_violations": metrics.schema_violations,
                "logs_with_context": metrics.logs_with_context,
                "avg_data_quality_score": metrics.avg_data_quality_score,
                "min_data_quality_score": metrics.min_data_quality_score,
                "max_data_quality_score": metrics.max_data_quality_score,
                "quality_status": metrics.quality_status,
                "avg_idle_ratio": metrics.avg_idle_ratio,
                "avg_typing_rate_per_min": metrics.avg_typing_rate_per_min,
                "avg_activity_intensity": metrics.avg_activity_intensity,
                "quality_degradation_flag": metrics.quality_degradation_flag,
                "high_violation_rate_flag": metrics.high_violation_rate_flag,
            }, status=status.HTTP_200_OK)
            
        except PermissionError as e:
            logger.warning(f"Unauthorized metrics request: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            logger.error(f"Error fetching quality metrics: {e}", exc_info=True)
            return Response(
                {"error": "Failed to fetch quality metrics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DataQualityTrendView(DeviceAuthMixin, APIView):
    """
    Get data quality trends over a date range.
    Useful for monitoring quality degradation over time.
    """

    def get(self, request):
        """
        Query parameters:
        - start_date: YYYY-MM-DD (required)
        - end_date: YYYY-MM-DD (required)
        - org_id: Organization ID (optional, defaults to device's org)
        """
        try:
            device = self._get_device_from_request(request)
            org = device.membership.organization if device.membership else None
            if not org:
                return Response(
                    {"error": "Device not associated with an organization"},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            org_id = request.query_params.get('org_id', org.id)
            
            # Verify user has access to this org
            if str(org_id) != str(org.id):
                return Response(
                    {"error": "Unauthorized access to organization"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            start_date_str = request.query_params.get('start_date')
            end_date_str = request.query_params.get('end_date')
            
            if not start_date_str or not end_date_str:
                return Response(
                    {"error": "start_date and end_date parameters (YYYY-MM-DD) are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Parse dates
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if start_date > end_date:
                return Response(
                    {"error": "start_date must be before end_date"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get metrics for date range
            metrics_list = DataQualityMetrics.objects.filter(
                date__gte=start_date,
                date__lte=end_date,
                organization__id=org_id
            ).order_by('date')
            
            trends = []
            for m in metrics_list:
                trends.append({
                    "date": m.date.isoformat(),
                    "total_logs": m.total_logs,
                    "valid_logs": m.valid_logs,
                    "avg_data_quality_score": m.avg_data_quality_score,
                    "quality_status": m.quality_status,
                    "schema_violations": m.schema_violations,
                    "quality_degradation_flag": m.quality_degradation_flag,
                })
            
            # Calculate overall trend
            if trends:
                first_score = trends[0]['avg_data_quality_score']
                last_score = trends[-1]['avg_data_quality_score']
                trend_direction = "improving" if last_score > first_score else "degrading" if last_score < first_score else "stable"
            else:
                trend_direction = "unknown"
            
            return Response({
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "organization_id": org_id,
                "trend_direction": trend_direction,
                "days_with_data": len(trends),
                "metrics": trends
            }, status=status.HTTP_200_OK)
            
        except PermissionError as e:
            logger.warning(f"Unauthorized trend request: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            logger.error(f"Error fetching quality trends: {e}", exc_info=True)
            return Response(
                {"error": "Failed to fetch quality trends"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

