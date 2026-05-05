"""Generate AI images — Imagen 3 (Google) primary, Pollinations fallback."""

from __future__ import annotations
import os
import time
import requests
from urllib.parse import quote


def _fetch_imagen(prompt: str, index: int, output_dir: str) -> str | None:
    """Generate image using Google Imagen 3 via Gemini API."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        result = client.models.generate_images(
            model="imagen-3.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="9:16",
                safety_filter_level="block_only_high",
            ),
        )
        if result.generated_images:
            image_bytes = result.generated_images[0].image.image_bytes
            path = os.path.join(output_dir, f"gen_{index:02d}.jpg")
            with open(path, "wb") as f:
                f.write(image_bytes)
            return path
    except Exception as e:
        print(f"[images] Imagen 3 error on image {index}: {e}")
    return None


def _fetch_pollinations(prompt: str, index: int, output_dir: str) -> str | None:
    """Generate image using Pollinations.ai (free fallback)."""
    full = f"{prompt}, cinematic, dramatic lighting, photorealistic, 8k, vertical portrait"
    url = (
        f"https://image.pollinations.ai/prompt/{quote(full)}"
        f"?width=1080&height=1920&nologo=true&seed={index * 42}"
    )
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 5000:
                path = os.path.join(output_dir, f"gen_{index:02d}.jpg")
                with open(path, "wb") as f:
                    f.write(resp.content)
                return path
            elif resp.status_code == 429:
                wait = 4 * (attempt + 1)
                print(f"[images] Rate limited, waiting {wait}s...")
                time.sleep(wait)
        except Exception as e:
            print(f"[images] Pollinations error: {e}")
            if attempt < 2:
                time.sleep(3)
    return None


def generate_images(prompts: list[str], output_dir: str) -> list[str]:
    """Generate portrait images for each prompt. Returns paths in order."""
    if not prompts:
        return []
    os.makedirs(output_dir, exist_ok=True)

    print(f"[images] Generating {len(prompts)} images via Pollinations...")

    paths = []
    for i, prompt in enumerate(prompts):
        if i > 0:
            time.sleep(1)

        path = None
        path = _fetch_pollinations(prompt, i, output_dir)

        if path:
            paths.append(path)
            print(f"[images] {len(paths)}/{len(prompts)} ready")
        else:
            print(f"[images] Skipped image {i}")

    print(f"[images] Done: {len(paths)}/{len(prompts)} generated.")
    return paths
