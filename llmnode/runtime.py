from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections import deque


class QueueFullError(Exception):
    pass


class QueueTimeoutError(Exception):
    pass


class ApiKeyRateLimitError(Exception):
    pass


class ApiKeyConcurrencyError(Exception):
    pass


@dataclass
class RuntimeState:
    request_id: str = ""
    request_count: int = 0
    active_requests: int = 0


class ApiKeyLease:
    def __init__(
        self,
        gate: "ApiKeyGate",
        key_id: int | None,
        *,
        rpm_token: int | None = None,
        concurrency_acquired: bool = False,
    ):
        self._gate = gate
        self._key_id = key_id
        self._rpm_token = rpm_token
        self._concurrency_acquired = concurrency_acquired
        self._closed = False

    async def reject(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._gate._rollback(
            self._key_id,
            rpm_token=self._rpm_token,
            concurrency_acquired=self._concurrency_acquired,
        )

    async def finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._gate._finish(self._key_id, concurrency_acquired=self._concurrency_acquired)


class ApiKeyGate:
    def __init__(self, window_seconds: float = 60.0):
        self._window_seconds = window_seconds
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._rpm_events: dict[int, deque[tuple[int, float]]] = {}
        self._active_counts: dict[int, int] = {}
        self._next_token = 0

    def _ensure_primitives(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop or self._lock is None:
            self._loop = loop
            self._lock = asyncio.Lock()
            self._rpm_events = {}
            self._active_counts = {}
            self._next_token = 0

    def _prune_events(self, key_id: int, now: float) -> None:
        events = self._rpm_events.get(key_id)
        if events is None:
            return
        while events and (now - events[0][1]) >= self._window_seconds:
            events.popleft()
        if not events:
            self._rpm_events.pop(key_id, None)

    def _remove_rpm_token(self, key_id: int, rpm_token: int) -> None:
        events = self._rpm_events.get(key_id)
        if events is None:
            return
        remaining = deque(item for item in events if item[0] != rpm_token)
        if remaining:
            self._rpm_events[key_id] = remaining
        else:
            self._rpm_events.pop(key_id, None)

    async def begin(
        self,
        key_id: int | None,
        *,
        rpm_limit: int | None,
        concurrency_limit: int | None,
    ) -> ApiKeyLease:
        if key_id is None:
            return ApiKeyLease(self, None)

        self._ensure_primitives()
        assert self._lock is not None

        async with self._lock:
            now = asyncio.get_running_loop().time()
            rpm_token: int | None = None
            if rpm_limit is not None:
                self._prune_events(key_id, now)
                events = self._rpm_events.setdefault(key_id, deque())
                if len(events) >= rpm_limit:
                    raise ApiKeyRateLimitError("api key rpm limit exceeded")
                self._next_token += 1
                rpm_token = self._next_token
                events.append((rpm_token, now))

            concurrency_acquired = False
            if concurrency_limit is not None:
                active = self._active_counts.get(key_id, 0)
                if active >= concurrency_limit:
                    if rpm_token is not None:
                        self._remove_rpm_token(key_id, rpm_token)
                    raise ApiKeyConcurrencyError("api key concurrency limit exceeded")
                self._active_counts[key_id] = active + 1
                concurrency_acquired = True

            return ApiKeyLease(
                self,
                key_id,
                rpm_token=rpm_token,
                concurrency_acquired=concurrency_acquired,
            )

    async def _rollback(
        self,
        key_id: int | None,
        *,
        rpm_token: int | None,
        concurrency_acquired: bool,
    ) -> None:
        if key_id is None:
            return
        self._ensure_primitives()
        assert self._lock is not None
        async with self._lock:
            if concurrency_acquired:
                active = self._active_counts.get(key_id, 0)
                if active <= 1:
                    self._active_counts.pop(key_id, None)
                else:
                    self._active_counts[key_id] = active - 1
            if rpm_token is not None:
                self._remove_rpm_token(key_id, rpm_token)

    async def _finish(self, key_id: int | None, *, concurrency_acquired: bool) -> None:
        if key_id is None or not concurrency_acquired:
            return
        self._ensure_primitives()
        assert self._lock is not None
        async with self._lock:
            active = self._active_counts.get(key_id, 0)
            if active <= 1:
                self._active_counts.pop(key_id, None)
            else:
                self._active_counts[key_id] = active - 1


class RequestGate:
    def __init__(self, execution_limit: int, queue_limit: int, wait_timeout: float = 30.0):
        self._execution_limit = execution_limit
        self._queue_limit = queue_limit
        self._semaphore: asyncio.Semaphore | None = None
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiting = 0
        self._wait_timeout = wait_timeout

    def _ensure_primitives(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop or self._semaphore is None or self._lock is None:
            self._loop = loop
            self._semaphore = asyncio.Semaphore(self._execution_limit)
            self._lock = asyncio.Lock()

    @property
    def waiting(self) -> int:
        return self._waiting

    @asynccontextmanager
    async def slot(self):
        self._ensure_primitives()
        assert self._lock is not None
        assert self._semaphore is not None
        async with self._lock:
            if self._waiting >= self._queue_limit:
                raise QueueFullError("request queue is full")
            self._waiting += 1
        try:
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=self._wait_timeout)
            except asyncio.TimeoutError as exc:
                raise QueueTimeoutError("request queue timed out") from exc
        finally:
            async with self._lock:
                self._waiting -= 1
        try:
            yield
        finally:
            self._semaphore.release()
