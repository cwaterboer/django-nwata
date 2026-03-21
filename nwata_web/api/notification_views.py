"""
REST API views for notifications.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from .models import Notification
import logging

logger = logging.getLogger(__name__)


# ==========================================
# SERIALIZERS
# ==========================================

class NotificationSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()
    recipient_email = serializers.SerializerMethodField()
    related_user_email = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'title', 'message', 'is_read',
            'actor_email', 'recipient_email', 'related_user_email',
            'metadata', 'created_at', 'read_at'
        ]
        read_only_fields = fields
    
    def get_actor_email(self, obj):
        return obj.actor.email if obj.actor else None
    
    def get_recipient_email(self, obj):
        return obj.recipient.email if obj.recipient else None
    
    def get_related_user_email(self, obj):
        return obj.related_user.email if obj.related_user else None


# ==========================================
# API VIEWS
# ==========================================

class NotificationListView(APIView):
    """
    GET /api/notifications/ - Get user's notifications
    
    Query Parameters:
    - limit: Max number of notifications (default: 20, max: 100)
    - unread_only: Boolean to filter only unread (default: false)
    - organization_id: Filter by organization (optional)
    - notification_type: Filter by type (optional)
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            limit = min(int(request.query_params.get('limit', 20)), 100)
            unread_only = request.query_params.get('unread_only', 'false').lower() == 'true'
            organization_id = request.query_params.get('organization_id')
            notification_type = request.query_params.get('notification_type')
            
            # Base query
            notifications = Notification.objects.filter(
                recipient=request.user,
                is_deleted=False
            ).order_by('-created_at')
            
            # Apply filters
            if unread_only:
                notifications = notifications.filter(is_read=False)
            
            if organization_id:
                notifications = notifications.filter(organization_id=organization_id)
            
            if notification_type:
                notifications = notifications.filter(notification_type=notification_type)
            
            # Paginate
            notifications = notifications[:limit]
            
            serializer = NotificationSerializer(notifications, many=True)
            
            # Get unread count
            unread_count = Notification.objects.filter(
                recipient=request.user,
                is_read=False,
                is_deleted=False
            ).count()
            
            return Response({
                'count': len(notifications),
                'unread_count': unread_count,
                'results': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching notifications: {e}")
            return Response(
                {'error': 'Failed to fetch notifications'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class NotificationDetailView(APIView):
    """
    Get /api/notifications/{id}/ - Get single notification
    Patch /api/notifications/{id}/ - Mark as read
    Delete /api/notifications/{id}/ - Soft delete notification
    """
    permission_classes = [IsAuthenticated]
    
    def get_notification(self, request, notification_id):
        """Helper to get notification with permission check"""
        notification = get_object_or_404(
            Notification,
            id=notification_id,
            recipient=request.user,
            is_deleted=False
        )
        return notification
    
    def get(self, request, notification_id):
        try:
            notification = self.get_notification(request, notification_id)
            serializer = NotificationSerializer(notification)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching notification: {e}")
            return Response(
                {'error': 'Notification not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def patch(self, request, notification_id):
        """Mark notification as read"""
        try:
            notification = self.get_notification(request, notification_id)
            
            # Mark as read
            if not notification.is_read:
                notification.mark_as_read()
            
            serializer = NotificationSerializer(notification)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return Response(
                {'error': 'Failed to mark notification as read'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def delete(self, request, notification_id):
        """Soft delete notification"""
        try:
            notification = self.get_notification(request, notification_id)
            notification.soft_delete()
            
            return Response(
                {'message': 'Notification deleted'},
                status=status.HTTP_204_NO_CONTENT
            )
            
        except Exception as e:
            logger.error(f"Error deleting notification: {e}")
            return Response(
                {'error': 'Failed to delete notification'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class NotificationUnreadCountView(APIView):
    """
    GET /api/notifications/unread-count/ - Get counts of unread notifications
    
    Query Parameters:
    - organization_id: Optional organization filter
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            organization_id = request.query_params.get('organization_id')
            
            qs = Notification.objects.filter(
                recipient=request.user,
                is_read=False,
                is_deleted=False
            )
            
            if organization_id:
                qs = qs.filter(organization_id=organization_id)
            
            unread_count = qs.count()
            
            # Get unread by type
            unread_by_type = {}
            for notification_type, _ in Notification.NOTIFICATION_TYPES:
                count = qs.filter(notification_type=notification_type).count()
                if count > 0:
                    unread_by_type[notification_type] = count
            
            return Response({
                'unread_count': unread_count,
                'unread_by_type': unread_by_type,
                'has_unread': unread_count > 0
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching unread count: {e}")
            return Response(
                {'error': 'Failed to fetch unread count'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class NotificationBulkMarkAsReadView(APIView):
    """
    POST /api/notifications/mark-as-read/ - Mark multiple notifications as read
    
    Body:
    {
        "notification_ids": [1, 2, 3],
        "organization_id": 1 (optional)
    }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            notification_ids = request.data.get('notification_ids', [])
            organization_id = request.data.get('organization_id')
            
            if not notification_ids:
                return Response(
                    {'error': 'notification_ids list required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get notifications
            qs = Notification.objects.filter(
                id__in=notification_ids,
                recipient=request.user,
                is_deleted=False
            )
            
            if organization_id:
                qs = qs.filter(organization_id=organization_id)
            
            # Mark as read
            updated_count = 0
            for notification in qs:
                if not notification.is_read:
                    notification.mark_as_read()
                    updated_count += 1
            
            return Response({
                'updated_count': updated_count,
                'requested_count': len(notification_ids)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error bulk marking as read: {e}")
            return Response(
                {'error': 'Failed to mark notifications as read'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
