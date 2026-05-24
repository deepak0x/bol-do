"""Tiny JSON-file persistence for debug chat sessions and call transcripts.

Files land in ./sessions/ relative to this module:
  chat-<id>.json   — debug chat session (rewritten on each turn)
  call-<sid>.json  — call meta + full transcript (written at call end)

Single-process, no locking. Fine for a hackathon demo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent / "sessions"
ROOT.mkdir(exist_ok=True)


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    return obj


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(_to_jsonable(data), indent=2, ensure_ascii=False))


def save_chat(session_id: str, session: dict) -> None:
    _write(ROOT / f"chat-{session_id}.json", session)


def save_call(call_sid: str, meta: dict, transcript: list) -> None:
    _write(ROOT / f"call-{call_sid}.json", {"meta": meta, "transcript": transcript})


def load_chat(session_id: str) -> dict | None:
    p = ROOT / f"chat-{session_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def load_call(call_sid: str) -> dict | None:
    p = ROOT / f"call-{call_sid}.json"
    return json.loads(p.read_text()) if p.exists() else None


def list_sessions() -> dict:
    chats = sorted(f.stem.removeprefix("chat-") for f in ROOT.glob("chat-*.json"))
    calls = sorted(f.stem.removeprefix("call-") for f in ROOT.glob("call-*.json"))
    return {"chats": chats, "calls": calls}


# --- Scheduled calls ---

def save_scheduled(sched_id: str, data: dict) -> None:
    _write(ROOT / f"scheduled-{sched_id}.json", data)


def load_scheduled(sched_id: str) -> dict | None:
    p = ROOT / f"scheduled-{sched_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def delete_scheduled(sched_id: str) -> bool:
    p = ROOT / f"scheduled-{sched_id}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def list_scheduled() -> list[dict]:
    out: list[dict] = []
    for f in sorted(ROOT.glob("scheduled-*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except Exception:
            continue
    return out
