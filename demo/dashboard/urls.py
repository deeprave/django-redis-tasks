from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("events/", views.events, name="events"),
    path("refresh/", views.refresh, name="refresh"),
    path("pulse/start/", views.pulse_start, name="pulse-start"),
    path("pulse/stop/", views.pulse_stop, name="pulse-stop"),
    path("summarise/now/", views.summarise_now, name="summarise-now"),
    path("summarise/later/", views.summarise_later, name="summarise-later"),
    path("probe/start/", views.probe_start, name="probe-start"),
]
