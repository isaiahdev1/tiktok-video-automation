"""YouTube upload retry queue — saves failed uploads and retries when quota resets."""

from __future__ import annotations
import json
import os
from datetime import datetime

QUEUE_FILE = os.path.join(os.path.dirname(__file__), "..", "output", "youtube_queue.json")


def enqueue(video_path: str, title: str, description: str, tags: list[str],
            privacy: str = "public", thumbnail_path: str | None = None) -> None:
    """Add a failed upload to the retry queue."""
    queue = _load()
    queue.append({
        "video_path": video_path,
        "title": title,
        "description": description,
        "tags": tags,
        "privacy": privacy,
        "thumbnail_path": thumbnail_path,
        "queued_at": datetime.now().isoformat(),
        "attempts": 0,
    })
    _save(queue)
    print(f"[yt-queue] Queued: '{title}' ({len(queue)} total pending)")


def retry_all() -> int:
    """Attempt to upload all queued videos. Returns count of successful uploads."""
    queue = _load()
    if not queue:
        print("[yt-queue] No videos in retry queue.")
        return 0

    print(f"[yt-queue] Retrying {len(queue)} queued uploads...")
    from src.youtube_uploader import upload_short

    remaining = []
    success_count = 0

    for item in queue:
        if not os.path.exists(item["video_path"]):
            print(f"[yt-queue] Skipping '{item['title']}' — file no longer exists.")
            continue

        item["attempts"] += 1
        try:
            video_id = upload_short(
                video_path=item["video_path"],
                title=item["title"],
                description=item["description"],
                tags=item["tags"],
                privacy=item["privacy"],
                thumbnail_path=item.get("thumbnail_path"),
            )
            url = f"https://www.youtube.com/shorts/{video_id}"
            print(f"[yt-queue] Uploaded: {url}")
            success_count += 1
        except Exception as e:
            err = str(e)
            print(f"[yt-queue] Still failed: '{item['title']}' — {err}")
            if item["attempts"] < 5:
                remaining.append(item)
            else:
                print(f"[yt-queue] Dropping '{item['title']}' after 5 attempts.")

    _save(remaining)
    print(f"[yt-queue] Done: {success_count} uploaded, {len(remaining)} still queued.")
    return success_count


def queue_size() -> int:
    return len(_load())


def _load() -> list[dict]:
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE) as f:
        return json.load(f)


def _save(queue: list[dict]) -> None:
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)
