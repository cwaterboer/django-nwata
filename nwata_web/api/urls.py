from django.urls import path

from .views import ActivityIngest

urlpatterns = [
    path('activity/', ActivityIngest.as_view(), name='activity-ingest'),
]