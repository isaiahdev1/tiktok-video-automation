"""Generate voiceover MP3 — ElevenLabs primary (natural), Edge TTS fallback (free)."""

from __future__ import annotations
import asyncio
import os
import random
import requests


# ElevenLabs voice IDs — varied for channel variety
_EL_VOICES = [
    "pNInz6obpgDQGcFmaJgB",  # Adam  — deep, authoritative
    "TxGEqnHWrfWFTfGW9XjX",  # Josh  — warm, conversational
    "ErXwobaYiN019PkySvjV",  # Antoni — natural, engaging
    "21m00Tcm4TlvDq8ikWAM",  # Rachel — clear, calm
]

# Edge TTS voices (fallback)
_EDGE_VOICES = [
    "en-US-AndrewNeural",
    "en-US-BrianNeural",
    "en-US-ChristopherNeural",
    "en-US-GuyNeural",
]


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
    voice_id = random.choice(_EL_VOICES)
    print(f"[voiceover] ElevenLabs voice: {voice_id}")

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.32,
                "similarity_boost": 0.78,
                "style": 0.42,
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

    voice = random.choice(_EDGE_VOICES)
    print(f"[voiceover] Edge TTS voice: {voice}")

    async def _run():
        tts = edge_tts.Communicate(text, voice)
        await tts.save(output_path)

    asyncio.run(_run())
    print(f"[voiceover] Saved to {output_path}")
    return output_path
