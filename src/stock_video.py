"""Fetch scene-matched stock video clips from Pexels."""

from __future__ import annotations
import os
import hashlib
import requests

PEXELS_SEARCH = "https://api.pexels.com/videos/search"
TARGET_W, TARGET_H = 1080, 1920


def fetch_scene_clips(queries: list[str], output_dir: str) -> list[str]:
    """
    Fetch one best-matching portrait clip per query (scene-matched B-roll).
    Returns clips in the same order as queries; missing scenes are skipped.
    """
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        print("[pexels] PEXELS_API_KEY not set — skipping.")
        return []

    os.makedirs(output_dir, exist_ok=True)
    headers = {"Authorization": api_key}
    paths = []

    for i, query in enumerate(queries):
        print(f"[pexels] Scene {i + 1}/{len(queries)}: '{query}'")
        clip = _fetch_one(query, i, output_dir, headers)
        if clip:
            paths.append(clip)
        else:
            # Try a shorter fallback query (first 2 words)
            short = " ".join(query.split()[:2])
            if short != query:
                print(f"[pexels]   Retrying with '{short}'")
                clip = _fetch_one(short, i, output_dir, headers)
                if clip:
                    paths.append(clip)

    print(f"[pexels] {len(paths)}/{len(queries)} clips ready.")
    return paths


def _fetch_one(query: str, index: int, output_dir: str, headers: dict) -> str | None:
    slug = hashlib.md5(query.encode()).hexdigest()[:8]
    cached = os.path.join(output_dir, f"clip_{index:02d}_{slug}.mp4")
    if os.path.exists(cached):
        print(f"[pexels]   Cached: {os.path.basename(cached)}")
        return cached

    try:
        resp = requests.get(
            PEXELS_SEARCH,
            headers=headers,
            params={"query": query, "per_page": 10, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
    except Exception as e:
        print(f"[pexels]   Search error: {e}")
        return None

    # Score each video: prefer portrait, HD, 8-30s duration
    best_url, best_score = None, -1
    for v in videos:
        dur = v.get("duration", 0)
        if dur < 4 or dur > 45:
            continue
        mp4s = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"]
        if not mp4s:
            continue
        # Pick highest resolution mp4
        best_file = max(mp4s, key=lambda f: f.get("width", 0) * f.get("height", 0))
        w, h = best_file.get("width", 0), best_file.get("height", 0)
        # Score: portrait ratio bonus + resolution
        portrait_bonus = 50 if h > w else 0
        score = portrait_bonus + min(w * h, 3840 * 2160) // 10000
        if score > best_score:
            best_score = score
            best_url = best_file.get("link")

    if not best_url:
        # Fallback: just take first available mp4 regardless of orientation
        for v in videos:
            mp4s = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"]
            if mp4s:
                best_file = max(mp4s, key=lambda f: f.get("width", 0) * f.get("height", 0))
                best_url = best_file.get("link")
                break

    if not best_url:
        print(f"[pexels]   No results for '{query}'")
        return None

    try:
        r = requests.get(best_url, stream=True, timeout=90)
        r.raise_for_status()
        with open(cached, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        size_mb = os.path.getsize(cached) / 1024 / 1024
        print(f"[pexels]   Downloaded {size_mb:.1f}MB → {os.path.basename(cached)}")
        return cached
    except Exception as e:
        print(f"[pexels]   Download error: {e}")
        if os.path.exists(cached):
            os.unlink(cached)
        return None


# Legacy function kept for backwards compat
def search_and_download_clips(
    keywords: list[str],
    output_dir: str,
    clips_per_keyword: int = 1,
    orientation: str = "portrait",
) -> list[str]:
    return fetch_scene_clips(keywords, output_dir)
