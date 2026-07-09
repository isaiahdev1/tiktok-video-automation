"""Generate portrait images per sentence.

Priority chain: Flux-Realism (fal.ai, paid) → Pexels photo (free) → Pollinations (free).
Set FAL_MAX_IMAGES to cap how many paid Flux calls a single run may make
(the rest fall through to the free sources); unset = no cap.
"""

from __future__ import annotations
import os
import time
import requests
from urllib.parse import quote


def _fetch_pexels_photo(query: str, index: int, output_dir: str) -> str | None:
    """Search Pexels for a portrait photo matching the query."""
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key or not query:
        return None
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query, "orientation": "portrait", "size": "large", "per_page": 5},
            timeout=15,
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            if photos:
                img_url = photos[0]["src"]["large2x"]
                img_resp = requests.get(img_url, timeout=30)
                if img_resp.status_code == 200:
                    path = os.path.join(output_dir, f"gen_{index:02d}.jpg")
                    with open(path, "wb") as f:
                        f.write(img_resp.content)
                    return path
    except Exception as e:
        print(f"[images] Pexels photo error on {index}: {e}")
    return None


def _fetch_flux(prompt: str, index: int, output_dir: str) -> str | None:
    """Generate image using Flux-Realism via fal.ai."""
    api_key = os.environ.get("FAL_KEY", "")
    if not api_key:
        return None
    full = (
        f"{prompt}, "
        "hyperrealistic photography, 8K ultra HD, award-winning shot, "
        "dramatic cinematic lighting, razor sharp focus, rich vivid colors, "
        "professional editorial quality, stunning visual, "
        "photorealistic, no text, no watermark, no logo"
    )
    try:
        resp = requests.post(
            "https://fal.run/fal-ai/flux-realism",
            headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
            json={
                "prompt": full,
                "image_size": {"width": 1080, "height": 1920},
                "num_inference_steps": 40,
                "guidance_scale": 3.5,
                "num_images": 1,
                "output_format": "jpeg",
                "enable_safety_checker": False,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            images = data.get("images", [])
            if images:
                img_url = images[0]["url"]
                img_resp = requests.get(img_url, timeout=60)
                if img_resp.status_code == 200:
                    path = os.path.join(output_dir, f"gen_{index:02d}.jpg")
                    with open(path, "wb") as f:
                        f.write(img_resp.content)
                    return path
        else:
            print(f"[images] Flux error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[images] Flux error on image {index}: {e}")
    return None


def _fetch_pollinations(prompt: str, index: int, output_dir: str) -> str | None:
    """Generate image using Pollinations.ai (free fallback)."""
    full = f"{prompt}, cinematic photography, sharp focus, vibrant colors, professional lighting, ultra-detailed, photorealistic, 8k, no text, no watermark, vertical portrait"
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


def generate_images(
    prompts: list[str],
    output_dir: str,
    search_queries: list[str] | None = None,
) -> list[str]:
    """Generate portrait images for each prompt. Returns paths in order.

    Priority chain per image:
      1. Flux-Realism via fal.ai (paid AI) — if FAL_KEY set, up to FAL_MAX_IMAGES
      2. Pexels photo search (free, real photography) — if search_query provided
      3. Pollinations.ai (free fallback)
    """
    if not prompts:
        return []
    os.makedirs(output_dir, exist_ok=True)

    use_flux = bool(os.environ.get("FAL_KEY"))
    use_pexels = bool(os.environ.get("PEXELS_API_KEY")) and bool(search_queries)
    prefer_ai = bool(os.environ.get("PREFER_AI_IMAGES"))  # free AI (Pollinations) before stock (Pexels)

    # Optional hard cap on paid Flux calls per run (cost guardrail).
    try:
        flux_budget = int(os.environ.get("FAL_MAX_IMAGES", "0"))
    except ValueError:
        flux_budget = 0
    flux_used = 0

    sources = []
    if use_flux:
        sources.append("Flux")
    if use_pexels:
        sources.append("Pexels")
    sources.append("Pollinations")
    print(f"[images] Generating {len(prompts)} images — priority: {' → '.join(sources)}")

    paths = []
    for i, prompt in enumerate(prompts):
        if i > 0:
            time.sleep(0.3)

        path = None
        query = (search_queries[i] if search_queries and i < len(search_queries) else "") or ""

        # 1. Flux — cinematic AI generation, purpose-built for each sentence
        within_budget = flux_budget <= 0 or flux_used < flux_budget
        if use_flux and within_budget:
            path = _fetch_flux(prompt, i, output_dir)
            if path:
                flux_used += 1
                print(f"[images] [{i+1}/{len(prompts)}] Flux ✓")
            else:
                print(f"[images] [{i+1}/{len(prompts)}] Flux failed, trying fallback...")
        elif use_flux and not within_budget:
            print(f"[images] [{i+1}/{len(prompts)}] Flux budget ({flux_budget}) reached — using free sources")

        # 2 & 3. Free fallbacks. With PREFER_AI_IMAGES, try Pollinations (custom AI, on-prompt)
        # BEFORE Pexels (generic stock) — an on-brand look without the paid Flux calls.
        order = ["pollinations", "pexels"] if prefer_ai else ["pexels", "pollinations"]
        for src in order:
            if path:
                break
            if src == "pexels" and use_pexels and query:
                path = _fetch_pexels_photo(query, i, output_dir)
                if path:
                    print(f"[images] [{i+1}/{len(prompts)}] Pexels ✓")
            elif src == "pollinations":
                path = _fetch_pollinations(prompt, i, output_dir)
                if path:
                    print(f"[images] [{i+1}/{len(prompts)}] Pollinations ✓")

        if path:
            paths.append(path)
        else:
            print(f"[images] [{i+1}/{len(prompts)}] All sources failed — skipping")

    print(f"[images] Done: {len(paths)}/{len(prompts)} generated.")
    return paths
