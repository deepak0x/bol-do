"""Bol Do — Pipecat bot definition.

This is the per-call pipeline: Twilio Media Stream WS → Deepgram STT →
OpenAI LLM → TTS (Cartesia placeholder, or Silk 1 once wired) → back to
Twilio. Adapted from the official pipecat-examples/twilio-chatbot/outbound
reference.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from dotenv import load_dotenv
from loguru import logger
from twilio.rest import Client as TwilioClient

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.adapters.services.gemini_adapter import GeminiLLMAdapter
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMRunFrame,
    LLMTextFrame,
    LLMThoughtTextFrame,
    TranscriptionFrame,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

import mailer
import session_store
from call_registry import registry
from prompts import build_system_prompt
from silk_tts import build_silk1_from_env
from transcript_hub import TranscriptEvent, hub
from dataclasses import asdict

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


# Per-call handles so the HTTP layer can inject text as the callee for debug.
live_calls: dict[str, dict] = {}


async def inject_callee_text(call_sid: str, text: str) -> bool:
    """Push a 'user' message into a live call's LLM context and kick inference.
    Returns False if no live call with that sid."""
    call = live_calls.get(call_sid)
    if not call:
        return False
    call["context"].add_message({"role": "user", "content": text})
    await call["task"].queue_frames([LLMRunFrame()])
    return True


def _build_tts(tone: str = "neutral"):
    provider = os.getenv("TTS_PROVIDER", "silk1").lower()
    if provider == "silk1":
        logger.info("Using Silk 1 TTS")
        return build_silk1_from_env(call_tone=tone)
    logger.info("Using Cartesia TTS (fallback)")
    return CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY", ""),
        voice_id=os.getenv("CARTESIA_VOICE_ID", "71a7ad14-091c-4e8e-a314-022ece01c121"),
    )


class TranscriptionNoiseFilter(FrameProcessor):
    """Drop short/noise TranscriptionFrames before they hit the LLM aggregator.

    Background noise on a phone line often gets transcribed as a single stray
    word ("hello", "actually"). Those trigger ghost LLM responses. We require
    at least `min_words` to count as a real callee utterance.
    """

    def __init__(self, min_words: int = 2):
        super().__init__()
        self._min_words = min_words

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            words = frame.text.strip().split()
            if len(words) < self._min_words:
                logger.info(f"noise-filter dropped: {frame.text!r} ({len(words)} word(s))")
                return  # swallow the frame
        await self.push_frame(frame, direction)


class TranscriptTap(FrameProcessor):
    """Sniffs LLM/STT frames and republishes turn-aggregated text to the UI hub.

    Callee side: each Deepgram TranscriptionFrame is a complete utterance — publish as-is.
    Agent side: LLMTextFrames stream token-by-token; buffer between
    LLMFullResponseStart/End and publish one bubble per turn (ignore thought tokens).
    """

    def __init__(self, call_sid: str, role: str):
        super().__init__()
        self._call_sid = call_sid
        self._role = role
        self._buf: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if self._role == "callee":
            if isinstance(frame, TranscriptionFrame) and frame.text.strip():
                await self._emit(frame.text.strip())
        elif self._role == "agent":
            if isinstance(frame, LLMFullResponseStartFrame):
                self._buf = []
            elif isinstance(frame, LLMTextFrame) and not isinstance(frame, LLMThoughtTextFrame):
                self._buf.append(frame.text)
            elif isinstance(frame, LLMFullResponseEndFrame):
                turn = "".join(self._buf).strip()
                self._buf = []
                if turn:
                    await self._emit(turn)

        await self.push_frame(frame, direction)

    async def _emit(self, text: str):
        await hub.publish(
            TranscriptEvent(
                call_sid=self._call_sid, role=self._role, text=text, ts=time.time()
            )
        )


async def run_bot(
    transport: BaseTransport,
    *,
    call_sid: str,
    task_text: str,
    tone: str,
    user_name: str,
    language: str = "hinglish",
    handle_sigint: bool,
):
    system_prompt = build_system_prompt(
        task=task_text, tone=tone, user_name=user_name, language=language
    )

    end_call_tool = FunctionSchema(
        name="end_call",
        description=(
            "Politely end the phone call. Only invoke after you have said a "
            "goodbye AND one of: goal confirmed by callee, callee refused, "
            "callee said bye, or call is a voicemail. Never invoke after "
            "only one exchange or when the callee has just asked a question."
        ),
        properties={
            "summary": {
                "type": "string",
                "description": "One short sentence describing what was achieved or what happened.",
            },
            "outcome": {
                "type": "string",
                "enum": ["success", "refused", "voicemail", "callee_ended", "unclear"],
                "description": "Best label for how this call ended.",
            },
        },
        required=["summary", "outcome"],
    )

    gemini_tools = GeminiLLMAdapter().to_provider_tools_format(
        ToolsSchema(standard_tools=[end_call_tool])
    )
    llm = GoogleLLMService(
        api_key=os.getenv("GEMINI_API_KEY", ""),
        settings=GoogleLLMService.Settings(
            model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            system_instruction=system_prompt,
        ),
        tools=gemini_tools,
    )

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY", ""))
    tts = _build_tts(tone=tone)

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    callee_tap = TranscriptTap(call_sid, role="callee")
    agent_tap = TranscriptTap(call_sid, role="agent")
    noise_filter = TranscriptionNoiseFilter(
        min_words=int(os.getenv("MIN_TRANSCRIPT_WORDS", "2"))
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            noise_filter,
            callee_tap,
            user_aggregator,
            llm,
            agent_tap,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Per-call hangup state (closure-captured by handler + watchdog + on_disconnect).
    hangup_state = {"done": False, "watchdog": None}
    # When did the bot's TTS audio actually finish? Updated by transport events.
    # Used by the silence watchdog so nudges don't fire while the bot is still speaking.
    speech_state = {"bot_finished_ts": 0.0}

    async def _do_hangup(outcome: str, summary: str) -> None:
        """Email the call report, wait for goodbye TTS to actually finish, then
        end the Twilio call via REST. Idempotent."""
        if hangup_state["done"]:
            return
        hangup_state["done"] = True

        meta_obj = registry.get(call_sid)
        transcript_pairs = [
            (ev.role, ev.text)
            for ev in hub.history(call_sid)
            if ev.role in ("agent", "callee")
        ]
        if meta_obj:
            mailer.send_call_report(
                to_number=meta_obj.to_number,
                task=meta_obj.task,
                tone=meta_obj.tone,
                outcome=outcome,
                summary=summary,
                transcript=transcript_pairs,
            )

        # Strict wait: let the pipeline pick up any in-flight text, then wait
        # for TTSStoppedFrame (real audio end), then a small breathing buffer.
        min_delay = float(os.getenv("GOODBYE_DELAY_SEC", "2"))
        pre_hangup_ts = time.time()
        await asyncio.sleep(min_delay)
        deadline = time.time() + 20  # hard ceiling so we never hang forever
        while time.time() < deadline:
            if speech_state["bot_finished_ts"] > pre_hangup_ts:
                break
            await asyncio.sleep(0.5)
        await asyncio.sleep(1.0)
        logger.info(f"[{call_sid}] tearing down call ({outcome})")

        try:
            client = TwilioClient(
                os.getenv("TWILIO_ACCOUNT_SID", ""),
                os.getenv("TWILIO_AUTH_TOKEN", ""),
            )
            client.calls(call_sid).update(status="completed")
            logger.info(f"[{call_sid}] Twilio hangup OK ({outcome})")
        except Exception as e:
            logger.error(f"[{call_sid}] Twilio hangup failed: {e}")

    async def _end_call_handler(params: FunctionCallParams) -> None:
        args = params.arguments or {}
        summary = str(args.get("summary", "")).strip()
        outcome = str(args.get("outcome", "unclear")).strip() or "unclear"

        bot_turns = sum(1 for ev in hub.history(call_sid) if ev.role == "agent")
        min_turns = int(os.getenv("MIN_TURNS_BEFORE_HANGUP", "2"))
        if bot_turns < min_turns:
            logger.warning(
                f"[{call_sid}] end_call REJECTED: bot_turns={bot_turns} < {min_turns}"
            )
            await params.result_callback(
                {"ended": False, "reason": "too_early, keep talking"}
            )
            return

        logger.info(f"[{call_sid}] end_call ACCEPTED: outcome={outcome} summary={summary!r}")
        await params.result_callback({"ended": True})
        asyncio.create_task(_do_hangup(outcome, summary))

    llm.register_function("end_call", _end_call_handler)

    async def _silence_watchdog() -> None:
        timeout = float(os.getenv("SILENCE_TIMEOUT_SEC", "30"))
        nudge_after = float(os.getenv("SILENCE_NUDGE_SEC", "15"))
        nudged_already = False
        while not hangup_state["done"]:
            await asyncio.sleep(1)
            history = hub.history(call_sid)
            agent_ts_list = [e.ts for e in history if e.role == "agent"]
            callee_ts_list = [e.ts for e in history if e.role == "callee"]
            if not agent_ts_list:
                # Bot hasn't even said its opener yet — nothing to time.
                continue
            # Use the moment the bot's audio actually FINISHED (from transport's
            # on_bot_stopped_speaking event), not when the text was published.
            # Falls back to text-publish ts until the first TTSStoppedFrame fires.
            bot_finished_ts = speech_state["bot_finished_ts"] or agent_ts_list[-1]
            last_callee_ts = callee_ts_list[-1] if callee_ts_list else 0.0
            # Before nudge: count silence from callee's last word (or bot's opener end
            # if callee never spoke). After nudge: also gate on bot's last audio end so
            # the hangup clock restarts AFTER the nudge audio actually finishes —
            # gives the callee ~SILENCE_TIMEOUT_SEC to respond to the nudge itself.
            if nudged_already:
                callee_baseline = max(last_callee_ts, bot_finished_ts)
            else:
                callee_baseline = last_callee_ts or bot_finished_ts
            silence_from_callee = time.time() - callee_baseline
            # Nudge baseline = any recent activity (so we don't nudge while bot talks).
            last_activity_ts = max(bot_finished_ts, last_callee_ts)
            silence_for_nudge = time.time() - last_activity_ts

            if silence_from_callee > timeout:
                logger.warning(f"[{call_sid}] silence timeout ({silence_from_callee:.1f}s) — saying goodbye then hanging up")
                pre_inject_ts = time.time()
                context.add_message(
                    {
                        "role": "user",
                        "content": (
                            "(the callee has not responded for a long time — say a brief "
                            "polite goodbye in one short Hinglish sentence, then we'll end the call)"
                        ),
                    }
                )
                await task.queue_frames([LLMRunFrame()])
                # Wait until the bot's audio for the goodbye has actually finished
                # (TTSStoppedFrame), with a hard ceiling so we never hang forever.
                deadline = time.time() + 20
                while time.time() < deadline:
                    await asyncio.sleep(0.5)
                    if speech_state["bot_finished_ts"] > pre_inject_ts:
                        break
                await asyncio.sleep(1.0)  # small breathing room after audio stops
                await _do_hangup(
                    "silence", f"No callee response for {silence_from_callee:.0f} seconds."
                )
                return
            if (
                not nudged_already
                and silence_for_nudge > nudge_after
                and last_activity_ts == bot_finished_ts  # only nudge after bot, not after our own nudge
            ):
                logger.info(f"[{call_sid}] silence nudge after {silence_for_nudge:.1f}s (one-shot)")
                context.add_message(
                    {
                        "role": "user",
                        "content": (
                            "(the callee has gone quiet for a few seconds — in one short "
                            "Hinglish sentence, naturally check if they are still on the line)"
                        ),
                    }
                )
                await task.queue_frames([LLMRunFrame()])
                nudged_already = True

    live_calls[call_sid] = {"task": task, "context": context}

    @transport.event_handler("on_bot_stopped_speaking")
    async def _on_bot_stopped(transport):
        speech_state["bot_finished_ts"] = time.time()

    @transport.event_handler("on_client_connected")
    async def _on_connect(transport, client):
        logger.info(f"[{call_sid}] callee answered, conversation starting")
        await hub.publish(
            TranscriptEvent(call_sid=call_sid, role="system", text="call connected", ts=time.time())
        )
        # Match the official pipecat outbound bootstrap: add a user-role
        # kick message *here* (not pre-seeded) then run the LLM. Pre-seeded
        # context messages don't reliably trigger the first inference.
        context.add_message(
            {"role": "user", "content": "(the call just connected — say your opening line now)"}
        )
        logger.info(f"[{call_sid}] context now has {len(context.messages)} msgs; queueing LLMRunFrame")
        await task.queue_frames([LLMRunFrame()])
        logger.info(f"[{call_sid}] LLMRunFrame queued")
        hangup_state["watchdog"] = asyncio.create_task(_silence_watchdog())

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnect(transport, client):
        logger.info(f"[{call_sid}] call ended")
        hangup_state["done"] = True
        wd = hangup_state.get("watchdog")
        if wd and not wd.done():
            wd.cancel()
        await hub.publish(
            TranscriptEvent(call_sid=call_sid, role="system", text="call ended", ts=time.time())
        )
        # Snapshot the full call (meta + transcript) to disk.
        meta_obj = registry.get(call_sid)
        meta_dict = asdict(meta_obj) if meta_obj else {"call_sid": call_sid}
        session_store.save_call(call_sid, meta_dict, hub.history(call_sid))
        await hub.close(call_sid)
        live_calls.pop(call_sid, None)
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Entry point invoked by server.py once Twilio's WS connects."""
    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    logger.info(f"Auto-detected telephony transport: {transport_type}")

    call_sid = call_data["call_id"]
    stream_sid = call_data["stream_id"]

    # Pull the task the user submitted (stored under call_sid by /dialout)
    meta = registry.get(call_sid)
    task_text = meta.task if meta else "Have a brief, friendly conversation."
    tone = meta.tone if meta else "neutral"
    user_name = meta.user_name if meta else "the user"
    language = meta.language if meta else "hinglish"

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    await run_bot(
        transport,
        call_sid=call_sid,
        task_text=task_text,
        tone=tone,
        user_name=user_name,
        language=language,
        handle_sigint=runner_args.handle_sigint,
    )
