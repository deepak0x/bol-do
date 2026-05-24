"""Bol Do FastAPI server.

Three endpoints:
  POST /dialout     — body: { to_number, task, tone?, user_name? } → starts a Twilio call
  POST /twiml       — Twilio webhook that returns <Connect><Stream> TwiML
  WS   /ws          — Twilio Media Streams connects here; bot runs here
  WS   /transcript  — Next.js UI connects here to stream the live transcript

Local dev: run `ngrok http 7860` and paste the https URL into LOCAL_SERVER_URL.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
from pydantic import BaseModel, Field
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

import asyncio
import uuid as _uuid_mod
from contextlib import asynccontextmanager

import scheduler
import session_store
from call_registry import CallMeta, registry
from prompts import build_system_prompt
from transcript_hub import TranscriptEvent, hub

load_dotenv(override=True)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    task = asyncio.create_task(scheduler.run_scheduler(_scheduler_place_call))
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="Bol Do", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


class DialoutBody(BaseModel):
    to_number: str = Field(..., description="E.164 number to call, e.g. +919876543210")
    task: str = Field(..., min_length=4, description="What the AI should accomplish on the call")
    tone: str = Field(default="neutral", pattern="^(polite|firm|neutral)$")
    user_name: str = Field(default="the user")
    language: str = Field(default="hinglish", pattern="^(hinglish|english)$")
    scheduled_for: str | None = Field(
        default=None,
        description="Optional ISO timestamp. If set, call is queued (not dialed now).",
    )


class DialoutResponse(BaseModel):
    call_sid: str
    to_number: str
    status: str


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise HTTPException(status_code=500, detail=f"Missing env var: {name}")
    return v


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "tts_provider": os.getenv("TTS_PROVIDER", "cartesia"),
        "have_twilio": bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN")),
        "have_deepgram": bool(os.getenv("DEEPGRAM_API_KEY")),
        "have_gemini": bool(os.getenv("GEMINI_API_KEY")),
        "local_server_url": os.getenv("LOCAL_SERVER_URL", ""),
    }


async def _place_twilio_call(
    *, to_number: str, task: str, tone: str, user_name: str, language: str = "hinglish"
) -> str:
    """Actually dial via Twilio + store meta. Returns the call_sid."""
    account_sid = _require_env("TWILIO_ACCOUNT_SID")
    auth_token = _require_env("TWILIO_AUTH_TOKEN")
    from_number = _require_env("TWILIO_FROM_NUMBER")
    local_url = _require_env("LOCAL_SERVER_URL")
    twiml_url = f"{local_url.rstrip('/')}/twiml"
    client = TwilioClient(account_sid, auth_token)
    call = client.calls.create(
        to=to_number, from_=from_number, url=twiml_url, method="POST"
    )
    meta = CallMeta(
        call_sid=call.sid,
        to_number=to_number,
        from_number=from_number,
        task=task,
        tone=tone,
        user_name=user_name,
        language=language,
    )
    registry.put(meta)
    session_store.save_call(call.sid, asdict(meta), [])
    logger.info(f"[{call.sid}] dial-out queued to {to_number}")
    return call.sid


async def _scheduler_place_call(entry: dict) -> str:
    return await _place_twilio_call(
        to_number=entry["to_number"],
        task=entry["task"],
        tone=entry.get("tone", "neutral"),
        user_name=entry.get("user_name", "the user"),
        language=entry.get("language", "hinglish"),
    )


@app.post("/dialout", response_model=DialoutResponse)
async def dialout(body: DialoutBody) -> DialoutResponse:
    # Schedule path
    if body.scheduled_for:
        sched_id = _uuid_mod.uuid4().hex[:12]
        entry = {
            "id": sched_id,
            "scheduled_for": body.scheduled_for,
            "to_number": body.to_number,
            "task": body.task,
            "tone": body.tone,
            "user_name": body.user_name,
            "language": body.language,
            "status": "pending",
            "fired_at": None,
            "call_sid": None,
            "created_at": time.time(),
        }
        session_store.save_scheduled(sched_id, entry)
        logger.info(f"scheduled-{sched_id}: queued for {body.scheduled_for}")
        return DialoutResponse(call_sid=sched_id, to_number=body.to_number, status="scheduled")
    # Immediate dial path
    try:
        sid = await _place_twilio_call(
            to_number=body.to_number,
            task=body.task,
            tone=body.tone,
            user_name=body.user_name,
            language=body.language,
        )
    except TwilioRestException as e:
        logger.warning(f"Twilio rejected dial-out to {body.to_number}: {e.msg}")
        raise HTTPException(status_code=400, detail=e.msg)
    return DialoutResponse(call_sid=sid, to_number=body.to_number, status="queued")


@app.get("/scheduled")
async def scheduled_list() -> list[dict]:
    return session_store.list_scheduled()


@app.delete("/scheduled/{sched_id}")
async def scheduled_cancel(sched_id: str) -> dict:
    entry = session_store.load_scheduled(sched_id)
    if not entry:
        raise HTTPException(status_code=404, detail="not found")
    if entry.get("status") == "pending":
        entry["status"] = "cancelled"
        session_store.save_scheduled(sched_id, entry)
    return {"ok": True, "status": entry.get("status")}


import uuid

# Debug-only in-memory chat sessions (mirrors a real call: server keeps history)
_chat_sessions: dict[str, dict] = {}


async def _gemini_reply(session: dict, user_message: str) -> str:
    from google import genai
    from google.genai import types as gtypes

    api_key = _require_env("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
    system_prompt = build_system_prompt(
        task=session["task"], tone=session["tone"], user_name=session["user_name"]
    )

    contents = []
    for turn in session["history"]:
        contents.append(
            gtypes.Content(role=turn["role"], parts=[gtypes.Part(text=turn["content"])])
        )
    contents.append(gtypes.Content(role="user", parts=[gtypes.Part(text=user_message)]))

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=gtypes.GenerateContentConfig(system_instruction=system_prompt),
    )
    text = (resp.text or "").strip()
    session["history"].append({"role": "user", "content": user_message})
    session["history"].append({"role": "model", "content": text})
    return text


class ChatStartBody(BaseModel):
    task: str = Field(..., min_length=4)
    tone: str = Field(default="neutral", pattern="^(polite|firm|neutral)$")
    user_name: str = Field(default="the user")


@app.post("/chat/start")
async def chat_start(body: ChatStartBody) -> dict:
    """Begin a text chat that mirrors a real call: bot speaks first, server
    keeps history. Returns session_id and the bot's opener."""
    session_id = uuid.uuid4().hex[:12]
    session = {
        "task": body.task,
        "tone": body.tone,
        "user_name": body.user_name,
        "history": [],
    }
    _chat_sessions[session_id] = session
    opener = await _gemini_reply(
        session,
        user_message="(the call just connected — say your opening line now)",
    )
    session_store.save_chat(session_id, session)
    return {"session_id": session_id, "opener": opener}


class ChatSayBody(BaseModel):
    message: str = Field(..., min_length=1)


@app.post("/chat/{session_id}/say")
async def chat_say(session_id: str, body: ChatSayBody) -> dict:
    session = _chat_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    reply = await _gemini_reply(session, user_message=body.message)
    session_store.save_chat(session_id, session)
    return {"reply": reply}


@app.get("/sessions")
async def sessions_list() -> dict:
    return session_store.list_sessions()


@app.get("/sessions/chat/{session_id}")
async def sessions_chat(session_id: str) -> dict:
    s = session_store.load_chat(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="chat session not found")
    return s


@app.get("/sessions/call/{call_sid}")
async def sessions_call(call_sid: str) -> dict:
    s = session_store.load_call(call_sid)
    if not s:
        raise HTTPException(status_code=404, detail="call session not found")
    return s


class InjectBody(BaseModel):
    message: str = Field(..., min_length=1)


@app.post("/inject/{call_sid}")
async def inject(call_sid: str, body: InjectBody) -> dict:
    """Inject text into a live call as if the callee said it. Useful when you
    can't speak (noisy room, debugging, faster iteration). The bot replies via
    Silk over the actual phone call."""
    from bot import inject_callee_text

    text = body.message.strip()
    # Show the typed text in the live transcript UI.
    await hub.publish(
        TranscriptEvent(call_sid=call_sid, role="callee", text=text, ts=time.time())
    )
    ok = await inject_callee_text(call_sid, text)
    if not ok:
        raise HTTPException(status_code=404, detail="no active call with that sid")
    return {"ok": True}


@app.get("/debug", response_class=HTMLResponse)
async def debug_chat() -> HTMLResponse:
    """Minimal browser chat to exercise the same prompt/LLM the live call uses."""
    return HTMLResponse(_DEBUG_HTML)


_DEBUG_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Bol Do — debug chat</title>
<style>
  body{font:14px/1.5 system-ui,sans-serif;background:#0a0a0a;color:#e5e5e5;margin:0;padding:24px;max-width:720px;margin:auto}
  h1{font-size:18px;margin:0 0 16px}
  label{display:block;font-size:12px;color:#888;margin:8px 0 2px}
  input,select,textarea{width:100%;background:#171717;color:#e5e5e5;border:1px solid #333;border-radius:6px;padding:8px;font:inherit;box-sizing:border-box}
  textarea{min-height:60px;resize:vertical}
  button{background:#fafafa;color:#000;border:0;border-radius:999px;padding:8px 16px;font-weight:600;cursor:pointer;margin-top:12px}
  button:disabled{opacity:.5;cursor:not-allowed}
  #log{margin-top:24px;border-top:1px solid #222;padding-top:16px;display:none}
  .msg{margin:8px 0;padding:8px 12px;border-radius:12px;max-width:80%}
  .bot{background:#1f1f1f;align-self:flex-start;margin-right:auto}
  .user{background:#fafafa;color:#000;align-self:flex-end;margin-left:auto}
  .meta{font-size:10px;text-transform:uppercase;opacity:.5;margin-bottom:2px}
  #log .chat{display:flex;flex-direction:column}
  #row{display:flex;gap:8px;margin-top:12px}
  #row input{flex:1}
  .sid{font-family:monospace;font-size:11px;color:#555}
</style></head><body>
<h1>Bol Do — debug chat (no phone, no audio)</h1>
<div id="setup">
  <label>Your name</label><input id="user_name" value="Deepak"/>
  <label>Task</label><textarea id="task">Book a table for 4 at 8 PM tonight. Window seat if possible. My name is Deepak.</textarea>
  <label>Tone</label>
  <select id="tone"><option>polite</option><option>neutral</option><option>firm</option></select>
  <button id="start">Start session</button>
</div>
<div id="log">
  <div class="sid" id="sid"></div>
  <div class="chat" id="chat"></div>
  <div id="row">
    <input id="msg" placeholder="Type as the callee…" autocomplete="off"/>
    <button id="send">Send</button>
  </div>
</div>
<script>
let session_id = null;
const $ = (id) => document.getElementById(id);
function bubble(role, text){
  const d = document.createElement('div');
  d.className = 'msg ' + (role === 'model' ? 'bot' : 'user');
  d.innerHTML = '<div class="meta">' + (role === 'model' ? 'Bol Do' : 'You') + '</div>' + text.replace(/&/g,'&amp;').replace(/</g,'&lt;');
  $('chat').appendChild(d);
  window.scrollTo(0, document.body.scrollHeight);
}
$('start').onclick = async () => {
  $('start').disabled = true;
  const r = await fetch('/chat/start', {method:'POST',headers:{'content-type':'application/json'},
    body: JSON.stringify({task:$('task').value,tone:$('tone').value,user_name:$('user_name').value})});
  const j = await r.json();
  session_id = j.session_id;
  $('sid').textContent = 'session: ' + session_id;
  $('setup').style.display='none';
  $('log').style.display='block';
  bubble('model', j.opener);
  $('msg').focus();
};
async function send(){
  const text = $('msg').value.trim();
  if(!text) return;
  bubble('user', text);
  $('msg').value=''; $('send').disabled=true;
  const r = await fetch('/chat/' + session_id + '/say', {method:'POST',headers:{'content-type':'application/json'},
    body: JSON.stringify({message: text})});
  const j = await r.json();
  bubble('model', j.reply);
  $('send').disabled=false;
  $('msg').focus();
}
$('send').onclick = send;
$('msg').addEventListener('keydown', e => { if(e.key==='Enter') send(); });
</script>
</body></html>
"""


@app.post("/twiml")
async def twiml(request: Request) -> HTMLResponse:
    """Twilio hits this once the call is initiated; we return TwiML that
    pipes call audio into our WebSocket."""
    local_url = _require_env("LOCAL_SERVER_URL")
    ws_url = local_url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws"

    form = await request.form()
    call_sid = form.get("CallSid", "")
    to_number = form.get("To", "")
    from_number = form.get("From", "")
    logger.info(f"[{call_sid}] /twiml → {ws_url}")

    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=ws_url)
    stream.parameter(name="call_sid", value=call_sid)
    stream.parameter(name="to_number", value=to_number)
    stream.parameter(name="from_number", value=from_number)
    connect.append(stream)
    response.append(connect)
    # Pad so the call doesn't drop while the WS handshake completes.
    response.pause(length=30)
    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/ws")
async def twilio_ws(websocket: WebSocket):
    """Twilio Media Streams connects here. Hands off to the Pipecat bot."""
    from bot import bot
    from pipecat.runner.types import WebSocketRunnerArguments

    await websocket.accept()
    logger.info("Twilio Media Streams WS accepted")
    try:
        await bot(WebSocketRunnerArguments(websocket=websocket))
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/transcript/{call_sid}")
async def transcript_ws(websocket: WebSocket, call_sid: str):
    """Next.js UI connects here for the live transcript stream."""
    await websocket.accept()
    logger.info(f"[{call_sid}] UI subscribed to transcript")
    try:
        async for ev in hub.subscribe(call_sid):
            await websocket.send_text(
                json.dumps(
                    {"call_sid": ev.call_sid, "role": ev.role, "text": ev.text, "ts": ev.ts}
                )
            )
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    logger.info(f"Bol Do server on :{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
