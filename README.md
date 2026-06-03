# Bol Do

> Type the call. Bol Do makes it. — Silk 1 hackathon project, 24 May 2026.

An AI that places real phone calls on your behalf. You type a task ("book a table for 4 at 8 PM", "complain about my delayed order"), Bol Do dials the number via Twilio and talks like a human in Hinglish. Live transcript in the browser; summary when the call ends.

## Demo Video

[Watch the demo](https://youtu.be/eQGTAPoLjIM?si=aYwo67eLgVSsvm75)

## Repo layout

```
bol-do/
├── CLAUDE.md          # project context for AI assistants
├── web/               # Next.js 16 frontend (App Router, TypeScript, Tailwind)
└── server/            # Python FastAPI + Pipecat backend
```

## What's wired right now

| Piece                        | Status      | Notes                                                            |
| ---------------------------- | ----------- | ---------------------------------------------------------------- |
| Next.js UI                   | done        | Task form, presets, tones, live transcript, dark mode            |
| FastAPI server               | done        | `/dialout`, `/twiml`, `/ws`, `/transcript/{call_sid}`, `/health` |
| Twilio outbound dialer       | done        | Uses `Connect+Stream` bidirectional TwiML                        |
| Deepgram streaming STT       | done        | via Pipecat `DeepgramSTTService`                                 |
| OpenAI LLM dialog manager    | done        | `gpt-4o-mini` by default, Hinglish + tone-aware system prompt    |
| Cartesia TTS (placeholder)   | done        | Real, works today — used until Silk 1 key arrives                |
| **Silk 1 TTS**               | **STUB**    | `server/silk_tts.py` raises `NotImplementedError`. Fill in at the event. |
| Transcript live stream to UI | done        | Single-process pub/sub (`transcript_hub.py`)                     |
| Call summary at end          | not yet     | Easy follow-up — last LLM turn into a "summary" message          |

Honest list. Nothing here pretends to work that doesn't.

## Local setup

### 1. Backend (Python 3.11+)

```bash
cd server
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp env.example .env
# fill in TWILIO_*, DEEPGRAM_API_KEY, OPENAI_API_KEY, CARTESIA_API_KEY
```

### 2. ngrok (so Twilio can reach your laptop)

```bash
ngrok http 7860
# copy the https URL into LOCAL_SERVER_URL in server/.env
```

### 3. Frontend (Node 20+)

```bash
cd web
pnpm install
cp .env.local.example .env.local   # default points at http://localhost:7860
pnpm dev
```

### 4. Run

```bash
# terminal A
cd server && source .venv/bin/activate && python server.py

# terminal B
cd web && pnpm dev
```

Open <http://localhost:3000>, type a task, pick a tone, hit **Place call**.

## Day-of-event: swap in Silk 1

1. Get `SILK1_API_KEY` from organizers.
2. Open `server/silk_tts.py` — fill in `Silk1TTSService.run_tts()` against the real Silk 1 streaming API. The class already conforms to Pipecat's `TTSService` interface, so no other file changes are needed.
3. In `.env`: set `TTS_PROVIDER=silk1` and `SILK1_API_KEY=...`.
4. Restart `server.py`. That's it.

## Demo plan (90 seconds)

1. Hook: "Who enjoys calling customer care?" — silence.
2. Pick the **Book a restaurant** preset. Number = pre-arranged friend playing "the business".
3. Hit Place Call → speakerphone on, room hears live call.
4. Friend asks a follow-up ("window seat ok?") — Bol Do answers in Hinglish.
5. Call ends → transcript on screen.
6. Close: "You never picked up the phone. Bol Do did — and they couldn't tell."

Backup: browser-simulated call (no Twilio) if the venue Wi-Fi or ngrok dies.

## Ethics

- The AI **must** disclose itself in its first sentence on every call (the system prompt enforces this).
- Only call willing parties for the demo. Don't cold-call strangers.

## Known gaps / nice-to-haves

- Call summary on hang-up (LLM "summarise this conversation" turn)
- Voicemail / IVR detection (Twilio AMD)
- Persistent storage (currently all in-memory; restart = forget)
- Auth on the dialout endpoint (open right now — don't expose ngrok URL publicly)
