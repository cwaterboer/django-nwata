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
from .models import ActivityLog, Gamification, User, Organization, Device, DeviceEvent

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
            device = Device.objects.select_related('user', 'user__org').get(token=token)
        except Device.DoesNotExist:
            raise PermissionError("Invalid device token")

        if require_active and device.token_expires_at < timezone.now():
            raise PermissionError("Device token expired")

        device.last_seen = timezone.now()
        device.save(update_fields=["last_seen"])
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

        # Map to analytics User
        try:
            nwata_user = User.objects.select_related('org').get(email=auth_user.email)
        except User.DoesNotExist:
            # Fallback: create organization if missing
            org, _ = Organization.objects.get_or_create(
                subdomain="default",
                defaults={"name": "Default Organization"}
            )
            nwata_user = User.objects.create(email=auth_user.email, org=org)

        device = Device.objects.create(
            user=nwata_user,
            name=device_name,
            token_expires_at=timezone.now(),  # will be set in _issue_device_token
        )

        token, expires_at = _issue_device_token(device)

        return Response({
            "token": token,
            "token_expires_at": expires_at.isoformat(),
            "user": {
                "email": nwata_user.email,
                "id": nwata_user.id,
            },
            "organization": {
                "id": nwata_user.org.id if nwata_user.org else None,
                "subdomain": nwata_user.org.subdomain if nwata_user.org else None,
                "name": nwata_user.org.name if nwata_user.org else None,
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

        return Response({
            "token": token,
            "token_expires_at": expires_at.isoformat(),
            "user": {
                "email": device.user.email,
                "id": device.user.id,
            },
            "organization": {
                "id": device.user.org.id if device.user.org else None,
                "subdomain": device.user.org.subdomain if device.user.org else None,
                "name": device.user.org.name if device.user.org else None,
            }
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
            org = device.user.org
            if org is None:
                raise ValueError("Device user is not associated with an organization")
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
                        self._process_single_log(log_entry, device.user)
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
                activity = self._process_single_log(data, device.user)
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
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid timestamp format: {str(e)}")

    def _process_single_log(self, log_data, user):
        """Process and create a single activity log entry for a specific user"""
        start_time = _parse_iso(log_data["start_time"])
        end_time = _parse_iso(log_data["end_time"])

        activity = ActivityLog.objects.create(
            user=user,
            app_name=log_data["app_name"],
            window_title=log_data.get("window_title", ""),
            start_time=start_time,
            end_time=end_time,
            category=log_data.get("category"),
        )

        logger.debug(
            f"Created ActivityLog {activity.id}: {activity.app_name} "
            f"({activity.duration:.1f}s)"
        )
        return activity


class DownloadAgent(APIView):
    """
    API endpoint for downloading the Nwata tracking agent.
    Serves a single zip containing all platform binaries.
    The agent detects its own OS at runtime.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        filename = 'nwata-agent.zip'
        
        # Build path to agent zip file
        agent_dir = os.path.join(settings.BASE_DIR, '..', 'nwata-agent')
        agent_path = os.path.join(agent_dir, filename)

        # Verify file exists
        if not os.path.exists(agent_path):
            logger.warning(f"Agent zip not found: {agent_path}")
            return Response(
                {"error": "Agent package not available"},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            response = FileResponse(
                open(agent_path, 'rb'),
                content_type='application/zip',
                as_attachment=True,
                filename=filename
            )
            logger.info(f"Agent download: {filename} served to {request.META.get('REMOTE_ADDR')}")
            return response
        except Exception as e:
            logger.error(f"Error serving agent download: {str(e)}")
            return Response(
                {"error": "Failed to download agent"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
