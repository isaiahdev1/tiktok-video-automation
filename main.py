"""
Automated TikTok/YouTube Shorts pipeline:
  1. Pick topic (Google Trends → Claude fallback, wealth niche)
  2. Generate script with Claude (includes image prompts, mood, hook)
  3. Generate voiceover with Edge TTS (random voice each video)
  4. Generate AI images via Flux-Realism (Pexels fallback, Pollinations last resort)
  5. Build MP4 (karaoke captions + mood music + SFX + hook overlay)
  6. Generate YouTube thumbnail
  7. Upload to TikTok and/or YouTube Shorts (failed uploads queued for retry)
  8. Log every upload to output/upload_log.csv

Flags:
  --retry-youtube   Retry all queued YouTube uploads and exit
  --stats           Print channel analytics and exit
  --batch N         Produce N videos sequentially
  --no-upload       Build videos locally without uploading
  --keep-intermediates  Keep per-run clips/images (default: auto-purge to save disk)

Note: by default each run deletes its own output/clips/<id> and output/images/<id>
scratch once the MP4 is built (output/final/ is kept). This prevents the clips
folder from filling the disk (it hit 15 GB twice in June 2026).
"""

from __future__ import annotations
import csv
import os
import random
import shutil
import sys
import time
import uuid
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.script_generator import generate_script
from src.voiceover import generate_voiceover
from src.video_editor import build_video
from src.topic_picker import get_next_topic
from src.notify import notify

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
LOG_FILE = os.path.join(OUTPUT_DIR, "upload_log.csv")


def run_pipeline(
    topic: str | None = None,
    upload_tiktok: bool = True,
    upload_youtube: bool = False,
    privacy: str = "public",
    keep_intermediates: bool = False,
) -> None:
    run_id = uuid.uuid4().hex[:8]

    # ── Topic ────────────────────────────────────────────────────
    if not topic:
        topic = get_next_topic()

    print(f"\n{'='*60}")
    print(f"  Topic: {topic}")
    print(f"{'='*60}\n")

    # ── Step 1: Script ───────────────────────────────────────────
    print("[1/6] Generating script...")
    script = generate_script(topic)
    print(f"      Title : {script['title']}")
    print(f"      Hook  : {script.get('hook', '')}")
    print(f"      Mood  : {script.get('mood', 'neutral')}")

    hook = script.get("hook") or script["narration"].split(".")[0].strip()
    mood = script.get("mood", "neutral")

    # ── Step 2: Voiceover ────────────────────────────────────────
    print("\n[2/6] Generating voiceover...")
    audio_path = os.path.join(OUTPUT_DIR, "audio", f"voiceover_{run_id}.mp3")
    generate_voiceover(script["narration"], audio_path)

    # ── Step 3: Visuals ──────────────────────────────────────────
    # AI images (Flux → Pexels → Pollinations) are the production style;
    # kinetic text cards are the always-works fallback if image gen returns
    # nothing (e.g. all sources down or out of budget).
    print("\n[3/6] Generating visuals [ai_images]...")
    clip_paths = []
    image_prompts = script.get("image_prompts", [])

    if image_prompts:
        from src.image_generator import generate_images
        search_queries = [
            s.get("search_query", "") for s in script.get("narration_segments", [])
            if isinstance(s, dict)
        ]
        clip_paths = generate_images(
            image_prompts,
            os.path.join(OUTPUT_DIR, "images", run_id),
            search_queries=search_queries or None,
        )

    if not clip_paths:
        print("      Image generation returned no clips — falling back to kinetic cards.")
        from src.kinetic_generator import generate_kinetic_clips
        clip_paths = generate_kinetic_clips(script, os.path.join(OUTPUT_DIR, "images", run_id))

    if not clip_paths:
        print("ERROR: No visuals generated.")
        sys.exit(1)

    print(f"      {len(clip_paths)} visuals ready.")

    # ── Step 4: Build video ──────────────────────────────────────
    print("\n[4/6] Building video (karaoke captions + mood music + hook)...")
    safe_title = "".join(
        c for c in script["title"] if c.isalnum() or c in " _-"
    )[:50]
    output_path = os.path.join(OUTPUT_DIR, "final", f"{safe_title}.mp4")

    segments = [s["text"] for s in script.get("narration_segments", []) if isinstance(s, dict)]
    build_video(
        clip_paths=clip_paths,
        audio_path=audio_path,
        output_path=output_path,
        hook_text=hook,
        mood=mood,
        segments=segments if len(segments) == len(clip_paths) else None,
    )

    # Cleanup audio file
    if os.path.exists(audio_path):
        os.unlink(audio_path)

    # Cleanup this run's intermediate visuals — the MP4 is built, so the
    # source clips/images are dead weight. (output/clips/ ballooned to 15 GB
    # twice and filled the disk; the final video lives in output/final/.)
    if not keep_intermediates:
        _cleanup_run_artifacts(run_id)

    # ── Step 5: Thumbnail ────────────────────────────────────────
    print("\n[5/6] Generating thumbnail...")
    thumbnail_path = None
    try:
        from src.thumbnail import generate_thumbnail
        thumbnail_path = os.path.join(OUTPUT_DIR, "thumbnails", f"{run_id}.jpg")
        generate_thumbnail(script["title"], thumbnail_path)
    except Exception as e:
        print(f"      Thumbnail failed (non-fatal): {e}")

    # ── Step 6: Upload ───────────────────────────────────────────
    print("\n[6/6] Uploading...")
    tiktok_ok = False
    youtube_url = ""

    if upload_tiktok:
        from src.tiktok_uploader import upload_to_tiktok
        tiktok_ok = upload_to_tiktok(
            video_path=output_path,
            caption=script["title"],
            tags=script["tags"][:5],
        )
        if tiktok_ok:
            print("[tiktok] Upload complete.")
        else:
            notify(f"TikTok upload could not be confirmed for: {script['title']}")

    if upload_youtube:
        from src.youtube_uploader import upload_short
        from src.youtube_queue import enqueue as yt_enqueue
        try:
            video_id = upload_short(
                video_path=output_path,
                title=script["title"],
                description=script["description"],
                tags=script["tags"],
                privacy=privacy,
                thumbnail_path=thumbnail_path,
            )
            youtube_url = f"https://www.youtube.com/shorts/{video_id}"
            print(f"[youtube] {youtube_url}")
        except Exception as e:
            err = str(e)
            print(f"[youtube] Upload failed: {err}")
            if "uploadLimitExceeded" in err or "quotaExceeded" in err or "forbidden" in err.lower():
                yt_enqueue(
                    video_path=output_path,
                    title=script["title"],
                    description=script["description"],
                    tags=script["tags"],
                    privacy=privacy,
                    thumbnail_path=thumbnail_path,
                )
                notify(f"YouTube upload failed (queued for retry): {script['title']} — {err}")
            else:
                print(f"[youtube] Not retryable: {err}")
                notify(f"YouTube upload failed (NOT retryable): {script['title']} — {err}")

    if not upload_tiktok and not upload_youtube:
        print(f"  Video saved: {output_path}")

    # ── Log ──────────────────────────────────────────────────────
    _log_upload(script["title"], youtube_url, tiktok_ok)

    # Alert if a scheduled run posted to nothing — the silent-outage guard.
    if (upload_tiktok or upload_youtube) and not tiktok_ok and not youtube_url:
        notify(f"Run posted to NOTHING: '{script['title']}' — both platforms failed.")

    print("\nDone!")


def _cleanup_run_artifacts(run_id: str) -> None:
    """Remove a run's intermediate scratch (downloaded clips + generated images).

    These accumulate per-run under output/clips/<run_id> and output/images/<run_id>
    and never get reused — the finished video is already in output/final/. Left
    unchecked they fill the disk (15 GB twice in June 2026). Safe + best-effort.
    """
    freed = 0
    for sub in ("clips", "images"):
        run_dir = os.path.join(OUTPUT_DIR, sub, run_id)
        if os.path.isdir(run_dir):
            for root, _dirs, files in os.walk(run_dir):
                for fn in files:
                    try:
                        freed += os.path.getsize(os.path.join(root, fn))
                    except OSError:
                        pass
            shutil.rmtree(run_dir, ignore_errors=True)
    if freed:
        print(f"      Cleaned {freed / 1024 / 1024:.0f} MB of intermediate clips/images.")


def _log_upload(title: str, youtube_url: str, tiktok_ok: bool) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    write_header = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["date", "title", "tiktok", "youtube_url"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            title,
            "ok" if tiktok_ok else "fail",
            youtube_url,
        ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Automated Shorts pipeline")
    parser.add_argument("--topic", default=None, help="Video topic (omit to auto-pick)")
    parser.add_argument("--no-tiktok", action="store_true", help="Skip TikTok upload")
    parser.add_argument("--youtube", action="store_true", help="Also upload to YouTube Shorts")
    parser.add_argument(
        "--privacy", choices=["private", "unlisted", "public"],
        default="public", help="YouTube privacy (default: public)"
    )
    parser.add_argument("--no-upload", action="store_true", help="Skip all uploads, save locally")
    parser.add_argument("--keep-intermediates", action="store_true", help="Keep per-run clips/images scratch (default: auto-delete to save disk)")
    parser.add_argument("--batch", type=int, default=1, help="Number of videos to produce (default: 1)")
    parser.add_argument("--interval", type=int, default=5, help="Minutes between batch videos (default: 5)")
    parser.add_argument("--retry-youtube", action="store_true", help="Retry all queued YouTube uploads and exit")
    parser.add_argument("--stats", action="store_true", help="Print channel analytics and exit")
    args = parser.parse_args()

    if args.retry_youtube:
        from src.youtube_queue import retry_all
        retry_all()
        sys.exit(0)

    if args.stats:
        from src.analytics import print_stats
        print_stats()
        sys.exit(0)

    for i in range(args.batch):
        if i > 0:
            print(f"\nWaiting {args.interval} minutes before next video...")
            time.sleep(args.interval * 60)

        try:
            run_pipeline(
                topic=args.topic if args.batch == 1 else None,
                upload_tiktok=not args.no_tiktok and not args.no_upload,
                upload_youtube=args.youtube and not args.no_upload,
                privacy=args.privacy,
                keep_intermediates=args.keep_intermediates,
            )
        except Exception as e:
            notify(f"Pipeline CRASHED before posting: {type(e).__name__}: {e}")
            raise
