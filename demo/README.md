# Redis Tasks Demo

A small Django dashboard that shows this package's Redis task backend: a
self-rescheduling pulse, a one-shot summariser (now or in 15 seconds), and a
probe that backs off with `run_after`. Redis is the only extra service.

This is a **localhost-only demo**. There is no database, authentication,
admin, or CSRF middleware. Bind `runserver` to `127.0.0.1` and do not expose
it on a network.

## Run it

Start Redis on localhost port 16399 (beside django-queues `demo_aq` 16379 and
`demo_pq` 16389):

```sh
docker compose up -d
```

From this `demo/` directory, install and deploy the django-queues Redis
Function library (required once per Redis):

```sh
uv sync
uv run python manage.py redis_lua_lib --deploy
```

Run the dashboard with Django's stock WSGI `runserver` (an ASGI server would
need extra dependencies this demo does not add):

```sh
uv run python manage.py runserver
```

In another terminal, start the worker:

```sh
uv run python manage.py runqueues
```

Open http://127.0.0.1:8000/ . Start the pulse, wait for a few samples, then
summarise or start the probe. Stop the pulse before starting it again.
Scheduled work sits in the **Scheduled** column until `run_after`, then
moves to **Done**. The worker does not run it early.

## How it works

Immediate summarise uses `aenqueue`. Delayed summarise and self-reschedule
use `enqueue` so `run_after` sticks under WSGI `runserver`. Submissions do
not call a raw queue publish. The worker is `RedisTaskWorker` plus
`handle_task_entry`. The page watches django-queues `queue_observer` over SSE;
the browser never talks to Redis.

Pulse appends JSON lines to `var/samples.jsonl` and enqueues the next
generation with `run_after` unless you press Stop. Summarise writes
`var/report.json`. Probe retries up to three attempts until three samples
exist.
