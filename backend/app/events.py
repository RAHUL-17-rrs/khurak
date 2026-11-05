"""Tiny in-process pub/sub -> Server-Sent Events. Safe to publish from worker threads."""
from __future__ import annotations

import asyncio
import json
import time
from collections import deque

_subscribers: set[asyncio.Queue] = set()
_loop: asyncio.AbstractEventLoop | None = None
recent: deque = deque(maxlen=300)


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def emit(event_type: str, /, **data) -> None:
    evt = {"type": event_type, "ts": time.time(), **data}
    recent.append(evt)
    msg = json.dumps(evt, ensure_ascii=False, default=str)

    def _push():
        for q in list(_subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    if _loop is None:
        return
    try:
        if asyncio.get_running_loop() is _loop:
            _push()
            return
    except RuntimeError:
        pass
    _loop.call_soon_threadsafe(_push)
