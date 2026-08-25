"""URL configuration for the Redis tasks demo."""

from django.urls import include, path

urlpatterns = [path("", include("dashboard.urls"))]
