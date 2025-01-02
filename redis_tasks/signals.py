from django.dispatch import Signal

__all__ = {"task_enqueued", "task_started", "task_finished"}

task_enqueued = Signal()
task_started = Signal()
task_finished = Signal()
