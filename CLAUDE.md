# Bol Do — Project Context for Claude

## What this is
**Bol Do** is an AI phone-call agent for the Silk 1 launch hackathon (Rumik AI, 24 May 2026, New Delhi). User types a task → backend places a real phone call via Twilio → an AI talks like a human in Hinglish → user gets a live transcript and final summary.

Hackathon idea is **LOCKED**. Don't propose new directions.

## Architecture
```
web (Next.js, App Router)          server (Python, FastAPI + Pipecat)
  task input form           ──▶    POST /dialout      (starts Twilio call)
  live transcript pane      ◀──    WS  /transcript    (relays bot transcript)
  outcome summary           ◀──    POST callback hook
                                    │
                                    ▼
                                   Twilio Voice
                                    │  (Media Streams WSS)
                                    ▼
                                   Pipecat pipeline:
                                     Deepgram STT
                                     → OpenAI LLM (dialog manager)
                                     → TTS (Cartesia placeholder → Silk 1 at event)
```

## Service stack (verified against pipecat-examples/twilio-chatbot/outbound)
- **Pipecat**: `pipecat-ai>=1.0.0` with extras `[websocket,deepgram,openai,silero,runner]`
- **Telephony**: Twilio Programmable Voice + Media Streams (`<Connect><Stream>` bidirectional)
- **STT**: Deepgram streaming
- **LLM**: OpenAI (gpt-4o-mini for low latency)
- **TTS placeholder**: Cartesia (real, works today)
- **TTS target**: Silk 1 — API key handed out at the event. There is a `silk_tts.py` stub that conforms to Pipecat's `TTSService` interface; we will fill in the HTTP/WS client once we have the key.

## What to do / not do
- **Do not** invent Pipecat APIs. The bot.py pipeline mirrors the official outbound example. If a class import is unclear, fetch from `github.com/pipecat-ai/pipecat-examples/tree/main/twilio-chatbot/outbound`.
- **Do not** claim Silk 1 is wired in. It is a stub until the event.
- **Do** keep TTS swappable via a single line in `bot.py`.
- **Do** keep things minimal — this is an 8-hour MVP, not a product.
- User wants short, plain replies. No long explanations unless asked. No buzzwords.

## Run order (local)
1. `cd server && uv venv && source .venv/bin/activate && uv pip install -r requirements.txt`
2. `cd server && cp env.example .env` → fill Twilio / Deepgram / OpenAI / Cartesia keys
3. `ngrok http 7860` → put `https://xxx.ngrok.io` in `LOCAL_SERVER_URL`
4. `cd server && python server.py`
5. `cd web && pnpm install && pnpm dev`
6. Open `http://localhost:3000`, type a task + a target number, hit "Place Call"

## Demo day swap (Silk 1)
- Set `SILK1_API_KEY` in `.env`
- Set `TTS_PROVIDER=silk1` in `.env`
- Restart the server. `bot.py` picks `Silk1TTSService` instead of `CartesiaTTSService`.

## Use cases (priority order for demo)
1. Restaurant booking (primary demo — pre-arranged friend as "the business")
2. Customer-care complaint
3. Clinic appointment enquiry

Tone shifts per intent — polite for bookings, firm but civil for complaints. Hinglish always.

## Persona rule (current)
**The bot does NOT disclose that it is AI** — by explicit user decision on 2026-05-24 for the hackathon demo. It opens like a normal Indian caller in Hinglish and, if asked whether it's a real person, deflects naturally rather than confirming AI. It does not actively claim to be human either (no outright lying). The legacy disclosure rule is intentionally overridden; do not re-introduce "main ek AI assistant hoon" without the user's explicit say-so.

## Use rule (still applies)
Pre-arrange callees, do not cold-call strangers for demo. The bot can hang up itself when work is done via the `end_call` tool; an email report is sent on every call end via Gmail SMTP.
