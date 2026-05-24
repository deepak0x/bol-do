"""In-memory pub/sub of call transcripts keyed by call_sid.

The Pipecat bot pushes transcript events here; the FastAPI WebSocket endpoint
that the Next.js UI connects to subscribes by call_sid and streams them out.

Single-process only — fine for a hackathon demo. Do not use in production.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class TranscriptEvent:
    call_sid: str
    role: str   # "agent" | "callee" | "system"
    text: str
    ts: float


@dataclass
class _CallChannel:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    history: list[TranscriptEvent] = field(default_factory=list)
    closed: bool = False


class TranscriptHub:
    def __init__(self) -> None:
        self._channels: dict[str, _CallChannel] = defaultdict(_CallChannel)
        self._lock = asyncio.Lock()

    async def publish(self, ev: TranscriptEvent) -> None:
        async with self._lock:
            ch = self._channels[ev.call_sid]
            ch.history.append(ev)
            await ch.queue.put(ev)

    async def close(self, call_sid: str) -> None:
        async with self._lock:
            ch = self._channels[call_sid]
            ch.closed = True
            await ch.queue.put(None)  # sentinel

    async def subscribe(self, call_sid: str) -> AsyncIterator[TranscriptEvent]:
        # Replay history so the UI can join mid-call and not miss anything.
        async with self._lock:
            ch = self._channels[call_sid]
            for ev in list(ch.history):
                yield ev
        while True:
            ev = await ch.queue.get()
            if ev is None:
                return
            yield ev

    def history(self, call_sid: str) -> list[TranscriptEvent]:
        return list(self._channels[call_sid].history)


# Singleton for the process.
hub = TranscriptHub()
