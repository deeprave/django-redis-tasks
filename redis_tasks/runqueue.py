import asyncio

__all__ = ("register_queue", "deregister_queue", "start_task_queues")

_registered_queues = {}
_registered_queues_lock = asyncio.Lock()


async def register_queue(name: str, instance) -> bool:
    async with _registered_queues_lock:
        if name not in _registered_queues:
            _registered_queues[name] = instance
            return True
        return False


async def deregister_queue(name: str) -> bool:
    async with _registered_queues_lock:
        if name in _registered_queues:
            del _registered_queues[name]
            return True
        return False


async def process_queues():

    while True:
        try:
            processed_count = 0

            async with _registered_queues_lock:
                # DEADLOCK warning:
                # Don't register or deregister queues in queued tasks!
                for name, queue in _registered_queues.items():
                    if await queue.dispatch():
                        processed_count += 1

            await asyncio.sleep(0.5 if processed_count else 2.5)

        # exit gracefully when the asyncio loop shuts down
        except asyncio.CancelledError:
            break


async def start_task_queues():
    # Add process_queues loop to asyncio main loop
    asyncio.create_task(process_queues())
