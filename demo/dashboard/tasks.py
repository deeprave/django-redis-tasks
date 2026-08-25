from datetime import timedelta

from django.tasks import task
from django.utils import timezone

from dashboard import catalogue


@task
def pulse(*, generation: int = 1) -> dict:
    result = catalogue.run_pulse(generation=generation)
    if result["reschedule"]:
        pulse.using(
            run_after=timezone.now() + timedelta(seconds=catalogue.PULSE_DELAY_SECONDS)
        ).enqueue(generation=generation + 1)
    return {key: value for key, value in result.items() if key != "reschedule"}


@task
async def summarise() -> dict:
    return catalogue.run_summarise()


@task
def probe(*, attempt: int = 1) -> dict:
    result = catalogue.run_probe(attempt=attempt)
    if "retry_in" in result:
        probe.using(
            run_after=timezone.now() + timedelta(seconds=int(result["retry_in"]))
        ).enqueue(attempt=attempt + 1)
    return result
