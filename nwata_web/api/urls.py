from django.urls import path

from .views import ActivityIngest, DeviceRegister, DeviceAuth, DeviceLifecycle, DownloadAgent, DataQualityMetricsView, DataQualityTrendView

urlpatterns = [
    path('device/register/', DeviceRegister.as_view(), name='device-register'),
    path('device/auth/', DeviceAuth.as_view(), name='device-auth'),
    path('device/lifecycle/', DeviceLifecycle.as_view(), name='device-lifecycle'),
    path('activity/', ActivityIngest.as_view(), name='activity-ingest'),
    path('agent/download/', DownloadAgent.as_view(), name='agent-download'),
    path('quality/metrics/', DataQualityMetricsView.as_view(), name='quality-metrics'),
    path('quality/trend/', DataQualityTrendView.as_view(), name='quality-trend'),
]