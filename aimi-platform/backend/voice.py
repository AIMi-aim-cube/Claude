"""
AIMi — Voice Assistant Service
==============================
Voice loop: audio in → STT → RAG answer → TTS → audio out.

STT: faster-whisper if installed (local, fast), else OpenAI-compatible
     /v1/audio/transcriptions endpoint (env STT_API_URL), else the browser's
     own Web Speech API handles transcription client-side (the dashboard
     does this by default, so the server STT is optional).
TTS: server-side via pyttsx3/edge-tts if installed; otherwise the dashboard
     uses browser SpeechSynthesis — zero infra needed for the MVP.

The single entry point voice_chat(audio|text) returns:
  {transcript, answer, sources, audio_b64?}
"""

from __future__ import annotations
import os
import io
import base64
import logging
import tempfile

import requests

from rag_pipeline import rag

log = logging.getLogger("aimi.voice")

STT_API_URL = os.getenv("STT_API_URL", "")
STT_API_KEY = os.getenv("STT_API_KEY", "")


class SpeechToText:
    def __init__(self):
        self._whisper = None
        try:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel("base", compute_type="int8")
            log.info("STT: faster-whisper (local)")
        except Exception:
            log.info("STT: %s", "remote API" if STT_API_URL else "browser-side only")

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        if self._whisper is not None:
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1] or ".webm") as f:
                f.write(audio_bytes)
                f.flush()
                segments, _ = self._whisper.transcribe(f.name)
                return " ".join(s.text for s in segments).strip()
        if STT_API_URL:
            r = requests.post(
                STT_API_URL.rstrip("/") + "/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {STT_API_KEY}"},
                files={"file": (filename, io.BytesIO(audio_bytes))},
                data={"model": "whisper-1"},
                timeout=60)
            r.raise_for_status()
            return r.json().get("text", "").strip()
        raise RuntimeError("No server-side STT configured — use browser Web Speech API "
                           "or set STT_API_URL.")


class TextToSpeech:
    def __init__(self):
        self._engine = None
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            log.info("TTS: pyttsx3 (local)")
        except Exception:
            log.info("TTS: browser SpeechSynthesis (client-side)")

    def synthesize(self, text: str) -> bytes | None:
        """Returns WAV bytes, or None when the client should speak it itself."""
        if self._engine is None:
            return None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            self._engine.save_to_file(text, path)
            self._engine.runAndWait()
            with open(path, "rb") as fh:
                return fh.read()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


stt = SpeechToText()
tts = TextToSpeech()


def voice_chat(text: str | None = None, audio_bytes: bytes | None = None,
               filename: str = "audio.webm", history: list | None = None,
               speak: bool = True) -> dict:
    """End-to-end voice turn. Provide either text (browser already
    transcribed) or raw audio bytes."""
    transcript = text or (stt.transcribe(audio_bytes, filename) if audio_bytes else "")
    if not transcript:
        return {"transcript": "", "answer": "I didn't catch that — try again?",
                "sources": [], "audio_b64": None}

    result = rag.answer(transcript, history=history)
    audio_b64 = None
    if speak:
        wav = tts.synthesize(result["answer"])
        if wav:
            audio_b64 = base64.b64encode(wav).decode()

    return {"transcript": transcript, **result, "audio_b64": audio_b64}
