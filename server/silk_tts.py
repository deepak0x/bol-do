"""Silk 1 TTS service for Rumik silk-api.

Streams audio via the one-shot WebSocket path:
  POST /v1/tts/ws-connect  ->  { ws_url, token }
  WS connect, send JSON synthesis frame, receive raw PCM int16 LE (24 kHz mono)
  binary frames, terminated by a `{"type":"done"}` text frame.

Pipecat downsamples to the transport's `audio_out_sample_rate` (8 kHz for
Twilio), so this service yields frames at Silk's native 24 kHz.
"""

from __future__ import annotations

import json
import os
from typing import AsyncGenerator, Optional

import httpx
import websockets
from loguru import logger
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService


SILK_DEFAULT_BASE = "https://silk-api.rumik.ai"
SILK_SAMPLE_RATE = 24000  # per Silk docs: raw PCM int16 LE, mono


class Silk1TTSService(TTSService):
    """Drop-in TTS service for Rumik Silk 1 (muga or mulberry)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "muga",
        tone: str = "neutral",
        description: Optional[str] = None,
        speaker: Optional[str] = None,
        f0_up_key: int = 0,
        api_base: str = SILK_DEFAULT_BASE,
        sample_rate: int = SILK_SAMPLE_RATE,
        **kwargs,
    ):
        super().__init__(
            sample_rate=sample_rate,
            settings=TTSSettings(model=model, voice=None, language=None),
            **kwargs,
        )
        if not api_key:
            raise ValueError("SILK1_API_KEY is empty — set it in .env")
        self._api_key = api_key
        self._model = model
        self._tone = tone
        self._description = description
        self._speaker = speaker
        self._f0_up_key = f0_up_key
        self._api_base = api_base.rstrip("/")
        logger.info(f"Silk1TTSService ready (model={model}, base={self._api_base})")

    def can_generate_metrics(self) -> bool:
        return True

    def _muga_text(self, text: str) -> str:
        # muga steers via a leading [tone] tag; add ours unless the LLM provided one.
        return text if text.lstrip().startswith("[") else f"[{self._tone}] {text}"

    def _synth_payload(self, text: str) -> dict:
        if self._model == "muga":
            return {"text": self._muga_text(text)}
        payload: dict = {"text": text, "f0_up_key": self._f0_up_key}
        if self._description:
            payload["description"] = self._description
        if self._speaker:
            payload["speaker"] = self._speaker
        return payload

    async def run_tts(
        self, text: str, context_id: str
    ) -> AsyncGenerator[Frame, None]:
        text = text.strip()
        if not text:
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._api_base}/v1/tts/ws-connect",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "text": text},
                )
                resp.raise_for_status()
                session = resp.json()
        except Exception as e:
            logger.error(f"Silk1 ws-connect failed: {e}")
            yield ErrorFrame(error=f"Silk1 ws-connect failed: {e}")
            return

        ws_url = session["ws_url"]
        token = session["token"]

        yield TTSStartedFrame(context_id=context_id)
        try:
            async with websockets.connect(f"{ws_url}?token={token}") as ws:
                await ws.send(json.dumps(self._synth_payload(text)))
                async for msg in ws:
                    if isinstance(msg, (bytes, bytearray)):
                        yield TTSAudioRawFrame(
                            audio=bytes(msg),
                            sample_rate=self.sample_rate,
                            num_channels=1,
                            context_id=context_id,
                        )
                    else:
                        try:
                            payload = json.loads(msg)
                        except json.JSONDecodeError:
                            continue
                        if payload.get("type") == "done":
                            break
                        if payload.get("error"):
                            logger.error(f"Silk1 stream error: {payload['error']}")
                            yield ErrorFrame(error=f"Silk1: {payload['error']}")
                            break
        except Exception as e:
            logger.exception(f"Silk1 streaming failed: {e}")
            yield ErrorFrame(error=f"Silk1 streaming failed: {e}")
        finally:
            yield TTSStoppedFrame(context_id=context_id)


# Map per-call LLM tone -> a sensible muga delivery tone.
TONE_TO_MUGA = {
    "polite": "happy",
    "neutral": "neutral",
    "firm": "neutral",
}


def build_silk1_from_env(call_tone: Optional[str] = None) -> Silk1TTSService:
    explicit = os.getenv("SILK1_TONE")
    tone = explicit or TONE_TO_MUGA.get(call_tone or "neutral", "neutral")
    return Silk1TTSService(
        api_key=os.getenv("SILK1_API_KEY", ""),
        model=os.getenv("SILK1_MODEL", "muga"),
        tone=tone,
        description=os.getenv("SILK1_DESCRIPTION") or None,
        speaker=os.getenv("SILK1_SPEAKER") or None,
        f0_up_key=int(os.getenv("SILK1_F0_UP_KEY", "0")),
        api_base=os.getenv("SILK1_API_BASE", SILK_DEFAULT_BASE),
    )
