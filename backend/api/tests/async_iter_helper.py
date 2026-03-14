"""
Utilities for consuming async generators from synchronous test code.

Usage:
    stream = response.streaming_content  # async generator
    it = SyncAsyncIter(stream)
    chunk = next(it)   # blocks until next item

How it works:
    - We start a dedicated event loop in a background thread.
    - Each `next(it)` call submits `anext(stream)` to that loop and
      waits for the result.  This keeps the same loop alive across
      successive `next()` calls, which is required for async generators
      to maintain their internal state.
"""
import asyncio
import concurrent.futures
import threading


class SyncAsyncIter:
    """Wrap an async iterable so it can be consumed synchronously from tests."""

    def __init__(self, async_iterable):
        self._aiter = async_iterable.__aiter__()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def __iter__(self):
        return self

    def __next__(self):
        future = asyncio.run_coroutine_threadsafe(self._aiter.__anext__(), self._loop)
        try:
            return future.result(timeout=10)
        except StopAsyncIteration:
            raise StopIteration
        except concurrent.futures.TimeoutError:
            raise TimeoutError("SSE stream read exceeded 10s")

    def close(self):
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)  # type: ignore
            self._thread.join(timeout=2)
        except Exception:
            pass
