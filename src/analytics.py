"""YouTube channel analytics — view counts, top videos, growth summary."""

from __future__ import annotations
import os
from datetime import datetime


def print_stats() -> None:
    """Print a summary of channel performance to stdout."""
    stats = get_channel_stats()
    if not stats:
        print("[analytics] Could not fetch stats.")
        return

    print("\n" + "=" * 50)
    print(f"  WEALTH VAULT — Channel Stats  ({datetime.now().strftime('%Y-%m-%d')})")
    print("=" * 50)
    print(f"  Subscribers : {_fmt(stats['subscribers'])}")
    print(f"  Total Views : {_fmt(stats['total_views'])}")
    print(f"  Video Count : {stats['video_count']}")
    print("=" * 50)

    videos = get_top_videos(limit=10)
    if videos:
        print("\n  Top Videos:")
        for i, v in enumerate(videos, 1):
            print(f"  {i:2}. {v['views']:>8} views  {v['likes']:>6} likes  {v['title'][:50]}")
    print()


def get_channel_stats() -> dict | None:
    """Return dict with subscribers, total_views, video_count."""
    svc = _build_service()
    if not svc:
        return None
    try:
        resp = svc.channels().list(part="statistics", mine=True).execute()
        items = resp.get("items", [])
        if not items:
            return None
        s = items[0]["statistics"]
        return {
            "subscribers": int(s.get("subscriberCount", 0)),
            "total_views": int(s.get("viewCount", 0)),
            "video_count": int(s.get("videoCount", 0)),
        }
    except Exception as e:
        print(f"[analytics] channel stats error: {e}")
        return None


def get_top_videos(limit: int = 10) -> list[dict]:
    """Return list of dicts: title, views, likes, url."""
    svc = _build_service()
    if not svc:
        return []
    try:
        # Get video IDs from uploads playlist
        ch_resp = svc.channels().list(
            part="contentDetails", mine=True
        ).execute()
        items = ch_resp.get("items", [])
        if not items:
            return []
        uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        pl_resp = svc.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_id,
            maxResults=50,
        ).execute()
        video_ids = [i["contentDetails"]["videoId"] for i in pl_resp.get("items", [])]
        if not video_ids:
            return []

        vid_resp = svc.videos().list(
            part="statistics,snippet",
            id=",".join(video_ids),
        ).execute()

        results = []
        for item in vid_resp.get("items", []):
            s = item.get("statistics", {})
            results.append({
                "title": item["snippet"]["title"],
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "url": f"https://www.youtube.com/shorts/{item['id']}",
            })

        results.sort(key=lambda x: x["views"], reverse=True)
        return results[:limit]

    except Exception as e:
        print(f"[analytics] top videos error: {e}")
        return []


def _build_service():
    """Build an authenticated YouTube API service."""
    try:
        import pickle
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request

        token_path = os.path.join(os.path.dirname(__file__), "..", "token.pickle")
        if not os.path.exists(token_path):
            print("[analytics] No token.pickle — run with --youtube first to authenticate.")
            return None

        with open(token_path, "rb") as f:
            creds = pickle.load(f)

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)

        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[analytics] service build error: {e}")
        return None


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)
