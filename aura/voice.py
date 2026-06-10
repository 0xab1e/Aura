"""Optional voice I/O. All dependencies are optional — if anything is
missing, the session falls back to text with a one-line install hint.

TTS: edge-tts (free, online) -> played with ffplay/afplay; fallback pyttsx3 (offline).
STT: faster-whisper (local) recording via sounddevice, push-to-talk style.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

VOICE = "en-US-GuyNeural"
SAMPLE_RATE = 16000

_whisper_model = None


def voice_available() -> tuple[bool, str]:
    """Return (ok, hint). Checks the imports without crashing."""
    missing = []
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        try:
            import pyttsx3  # noqa: F401
        except ImportError:
            missing.append("edge-tts (or pyttsx3)")
    try:
        import faster_whisper  # noqa: F401
        import sounddevice  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        missing.append("faster-whisper sounddevice numpy")
    if missing:
        return False, ("Voice mode needs: pip install " + " ".join(missing)
                       + " — continuing in text mode.")
    return True, ""


def speak(text: str) -> None:
    """Speak text aloud; silently degrade to no-op on any failure."""
    try:
        import asyncio
        import edge_tts

        async def _gen(path: str):
            await edge_tts.Communicate(text, VOICE).save(path)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
        asyncio.run(_gen(path))
        player = shutil.which("ffplay") or shutil.which("afplay") or shutil.which("mpv")
        if player:
            args = [player, path]
            if "ffplay" in player:
                args = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", path]
            subprocess.run(args, check=False)
        Path(path).unlink(missing_ok=True)
        return
    except Exception:
        pass
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass  # voice is best-effort; the text is already on screen


def listen() -> str:
    """Push-to-talk: Enter to start recording, Enter to stop. Returns transcript."""
    global _whisper_model
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel

    if _whisper_model is None:
        print("(loading speech model — first time only…)")
        _whisper_model = WhisperModel("base.en", compute_type="int8")

    input("🎙  Press Enter to START recording…")
    chunks = []

    def callback(indata, frames, time_info, status):
        chunks.append(indata.copy())

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", callback=callback)
    with stream:
        input("🎙  Recording — press Enter to STOP.")

    if not chunks:
        return ""
    audio = np.concatenate(chunks).flatten()
    segments, _ = _whisper_model.transcribe(audio, language="en")
    return " ".join(seg.text.strip() for seg in segments).strip()
