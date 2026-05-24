"""Maps Twilio call_sid → task metadata so the bot pipeline knows what to say.

The /dialout endpoint creates the entry. The /ws WebSocket endpoint reads it
when Twilio connects. In-memory, single-process — fine for the demo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CallMeta:
    call_sid: str
    to_number: str
    from_number: str
    task: str
    tone: str = "neutral"
    user_name: str = "the user"
    language: str = "hinglish"  # "hinglish" | "english"


class CallRegistry:
    def __init__(self) -> None:
        self._by_sid: dict[str, CallMeta] = {}

    def put(self, meta: CallMeta) -> None:
        self._by_sid[meta.call_sid] = meta

    def get(self, call_sid: str) -> CallMeta | None:
        return self._by_sid.get(call_sid)

    def all(self) -> list[CallMeta]:
        return list(self._by_sid.values())


registry = CallRegistry()
