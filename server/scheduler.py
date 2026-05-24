"""Background poller that fires scheduled Bol Do calls when their time arrives.

Scheduled entries live under sessions/scheduled-<id>.json. Format:
  {
    "id": "uuid", "scheduled_for": "ISO ts", "to_number": "+91…",
    "task": "…", "tone": "polite", "user_name": "Deepak",
    "status": "pending" | "fired" | "missed" | "cancelled",
    "fired_at": ISO ts | null, "call_sid": str | null
  }

Polls every POLL_INTERVAL_SEC. Fires entries where now >= scheduled_for.
Marks as 'missed' if more than GRACE_MIN minutes overdue (server was down).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from loguru import logger

import session_store


POLL_INTERVAL_SEC = 30
GRACE_MIN = 30  # entries more than this many minutes overdue are marked missed
IST = timezone(timedelta(hours=5, minutes=30))


def _parse_ts(ts: str) -> datetime:
    """Parse ISO ts. If no timezone offset, assume IST."""
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        # very old python style fallback
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt


async def run_scheduler(place_call: Callable[[dict], Awaitable[str]]) -> None:
    """Background loop. `place_call(meta_dict)` should dial the call and
    return the Twilio call_sid."""
    logger.info(f"Scheduler started (poll={POLL_INTERVAL_SEC}s, grace={GRACE_MIN}min)")
    while True:
        try:
            await _tick(place_call)
        except Exception as e:
            logger.exception(f"scheduler tick failed: {e}")
        await asyncio.sleep(POLL_INTERVAL_SEC)


async def _tick(place_call: Callable[[dict], Awaitable[str]]) -> None:
    now = datetime.now(IST)
    for entry in session_store.list_scheduled():
        if entry.get("status") != "pending":
            continue
        try:
            due = _parse_ts(entry["scheduled_for"])
        except Exception as e:
            logger.warning(f"scheduled-{entry.get('id')}: bad scheduled_for ({e})")
            continue
        if now < due:
            continue
        # Time to fire (or mark missed).
        overdue = (now - due).total_seconds() / 60
        if overdue > GRACE_MIN:
            entry["status"] = "missed"
            entry["fired_at"] = None
            session_store.save_scheduled(entry["id"], entry)
            logger.warning(f"scheduled-{entry['id']}: missed ({overdue:.0f}min overdue)")
            continue
        try:
            logger.info(f"scheduled-{entry['id']}: firing (due {due.isoformat()})")
            sid = await place_call(entry)
            entry["status"] = "fired"
            entry["fired_at"] = now.isoformat()
            entry["call_sid"] = sid
            session_store.save_scheduled(entry["id"], entry)
        except Exception as e:
            logger.exception(f"scheduled-{entry['id']}: failed to fire: {e}")
            entry["status"] = "missed"
            entry["fired_at"] = now.isoformat()
            entry["error"] = str(e)
            session_store.save_scheduled(entry["id"], entry)
