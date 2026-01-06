from django.urls import path

from .views import ActivityIngest, DeviceRegister, DeviceAuth, DeviceLifecycle, DownloadAgent

urlpatterns = [
    path('device/register/', DeviceRegister.as_view(), name='device-register'),
    path('device/auth/', DeviceAuth.as_view(), name='device-auth'),
    path('device/lifecycle/', DeviceLifecycle.as_view(), name='device-lifecycle'),
    path('activity/', ActivityIngest.as_view(), name='activity-ingest'),
    path('agent/download/', DownloadAgent.as_view(), name='agent-download'),
]