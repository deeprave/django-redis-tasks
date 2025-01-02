This project is currently incomplete, but is being published as a proof of concept.
While it works, it is not yet ready for production.

The following features are planned for the near future:

- Tasks are currently individually dispatched the queued and awaited until completion.

> This is not ideal for performance, where tasks are dispatched and awaited in sequence.
> Tasks should be dispatched and awaited in parallel so that long and forever running
> tasks don't block the queue.

- Make better use of contemporary asyncio features and use asyncio tasks instead of
  simply calling coroutines.

- Add support for `enqueue_on_commit`

- Add support for expired task cleanup.

- Possibly? add an admin UI for queues and redis-queued tasks.
