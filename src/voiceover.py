"""Generate voiceover MP3 — ElevenLabs primary (natural), Edge TTS fallback (free)."""

from __future__ import annotations
import asyncio
import os
import requests


# ONE consistent channel voice. A recognizable voice is part of channel
# identity — randomizing it every video (the old behaviour) trained the
# audience to hear a different narrator each time and killed recall. Default is
# Adam (deep, authoritative — suits fact content); override with the
# ELEVENLABS_VOICE_ID env var (already present in .env but previously ignored).
_DEFAULT_VOICE = "pNInz6obpgDQGcFmaJgB"  # Adam

# Edge TTS fallback — one consistent voice (Andrew: warm, natural).
_EDGE_VOICE = "en-US-AndrewNeural"


def generate_voiceover(text: str, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if api_key:
        try:
            return _elevenlabs(text, output_path, api_key)
        except Exception as e:
            print(f"[voiceover] ElevenLabs failed ({e}), falling back to Edge TTS...")

    return _edge(text, output_path)


def _elevenlabs(text: str, output_path: str, api_key: str) -> str:
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or _DEFAULT_VOICE
    model_id = os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2"
    print(f"[voiceover] ElevenLabs voice: {voice_id} ({model_id})")

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": text,
            "model_id": model_id,
            # Lower stability + higher style = more dynamic, expressive delivery
            # (flat narration is a big reason AI-slop videos get scrolled past).
            "voice_settings": {
                "stability": 0.30,
                "similarity_boost": 0.80,
                "style": 0.50,
                "use_speaker_boost": True,
            },
        },
        timeout=60,
    )
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(resp.content)
    print(f"[voiceover] Saved to {output_path}")
    return output_path


def _edge(text: str, output_path: str) -> str:
    import edge_tts

    voice = _EDGE_VOICE
    print(f"[voiceover] Edge TTS voice: {voice}")

    async def _run():
        tts = edge_tts.Communicate(text, voice)
        await tts.save(output_path)

    asyncio.run(_run())
    print(f"[voiceover] Saved to {output_path}")
    return output_path
