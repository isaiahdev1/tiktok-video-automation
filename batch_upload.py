"""
Upload all local videos in output/final/ to TikTok + YouTube.
Skips temp files. Queues YouTube uploads that hit quota.

Usage:
  python batch_upload.py              # both platforms
  python batch_upload.py --no-tiktok  # YouTube only
  python batch_upload.py --no-youtube # TikTok only
"""

from __future__ import annotations
import argparse
import os
import time
from dotenv import load_dotenv

load_dotenv()

FINAL_DIR = os.path.join(os.path.dirname(__file__), "output", "final")


def _all_videos() -> list[str]:
    files = sorted(
        f for f in os.listdir(FINAL_DIR)
        if f.endswith(".mp4") and not f.startswith("_")
    )
    return [os.path.join(FINAL_DIR, f) for f in files]


def _title_from_path(path: str) -> str:
    name = os.path.splitext(os.path.basename(path))[0]
    # Restore common punctuation lost in filename sanitization
    return name.replace("  ", " & ").strip()


def run(do_tiktok: bool, do_youtube: bool) -> None:
    videos = _all_videos()
    print(f"Found {len(videos)} videos in output/final/")
    print(f"Platforms: {'TikTok' if do_tiktok else ''} {'YouTube' if do_youtube else ''}\n")

    tiktok_ok = 0
    youtube_ok = 0
    youtube_queued = 0

    for i, path in enumerate(videos, 1):
        title = _title_from_path(path)
        print(f"[{i}/{len(videos)}] {title}")

        # ── TikTok ────────────────────────────────────────────────
        if do_tiktok:
            try:
                from src.tiktok_uploader import upload_to_tiktok
                ok = upload_to_tiktok(
                    video_path=path,
                    caption=title,
                    tags=["facts", "shorts", "didyouknow", "mindblown", "viral"],
                )
                if ok:
                    print(f"  [tiktok] ✓")
                    tiktok_ok += 1
                else:
                    print(f"  [tiktok] failed")
            except Exception as e:
                print(f"  [tiktok] error: {e}")
            time.sleep(5)

        # ── YouTube ───────────────────────────────────────────────
        if do_youtube:
            from src.youtube_uploader import upload_short
            from src.youtube_queue import enqueue as yt_enqueue
            description = (
                f"{title}\n\n"
                "#Shorts #Facts #DidYouKnow #MindBlown #Learning"
            )
            tags = ["facts", "shorts", "didyouknow", "mindblown", "science",
                    "psychology", "viral", "educational", "interesting", "amazing"]
            try:
                video_id = upload_short(
                    video_path=path,
                    title=title[:100],
                    description=description,
                    tags=tags,
                    privacy="public",
                )
                url = f"https://www.youtube.com/shorts/{video_id}"
                print(f"  [youtube] ✓  {url}")
                youtube_ok += 1
            except Exception as e:
                err = str(e)
                print(f"  [youtube] failed: {err[:120]}")
                if any(k in err for k in ("uploadLimitExceeded", "quotaExceeded", "forbidden", "Forbidden")):
                    yt_enqueue(path, title[:100], description, tags, "public")
                    youtube_queued += 1
                    print(f"  [youtube] queued for retry ({youtube_queued} total queued)")

            time.sleep(3)

        print()

    print("=" * 50)
    if do_tiktok:
        print(f"TikTok : {tiktok_ok}/{len(videos)} uploaded")
    if do_youtube:
        print(f"YouTube: {youtube_ok}/{len(videos)} uploaded, {youtube_queued} queued")
    if youtube_queued:
        print("Run 'python main.py --retry-youtube' tomorrow to upload the rest.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-tiktok", action="store_true")
    parser.add_argument("--no-youtube", action="store_true")
    args = parser.parse_args()
    run(do_tiktok=not args.no_tiktok, do_youtube=not args.no_youtube)
