from datetime import timedelta

from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from dashboard import catalogue
from dashboard.projection import projection
from dashboard.tasks import probe, pulse, summarise


def index(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/index.html")


@require_GET
def events(request: HttpRequest) -> StreamingHttpResponse:
    projection.start()
    response = StreamingHttpResponse(
        projection.events(), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_POST
def refresh(request: HttpRequest) -> HttpResponse:
    projection.refresh()
    return redirect("index")


@require_POST
def pulse_start(request: HttpRequest) -> HttpResponse:
    if catalogue.pulse_running():
        return redirect("index")
    catalogue.clear_pulse_stop()
    catalogue.mark_pulse_running()
    pulse.enqueue(generation=1)
    return redirect("index")


@require_POST
def pulse_stop(request: HttpRequest) -> HttpResponse:
    catalogue.request_pulse_stop()
    return redirect("index")


@require_POST
async def summarise_now(request: HttpRequest) -> HttpResponse:
    await summarise.aenqueue()
    return redirect("index")


@require_POST
def summarise_later(request: HttpRequest) -> HttpResponse:
    # Use enqueue, not aenqueue: Django's WSGI runserver runs async views on a
    # nested loop, and that path was dispatching deferred work immediately.
    summarise.using(
        run_after=timezone.now() + timedelta(seconds=catalogue.SUMMARISE_DELAY_SECONDS)
    ).enqueue()
    return redirect("index")


@require_POST
def probe_start(request: HttpRequest) -> HttpResponse:
    probe.enqueue(attempt=1)
    return redirect("index")
