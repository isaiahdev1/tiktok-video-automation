"""
Auto-comment on trending TikTok videos to drive profile visits and follows.

Strategy:
- Browse hashtag pages matching our content themes
- For each video, use Claude to write a genuine, relevant comment
- Post slowly with random delays to mimic human behavior
- Never comment on the same video twice
- Hard cap: 8 comments per run
"""

from __future__ import annotations
import json
import os
import random
import time
import anthropic

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "..", "tiktok_cookies.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "output", "comment_log.json")

# Hashtags to browse — matches the type of content we post
HASHTAGS = [
    "didyouknow", "funfacts", "learnontiktok", "sciencefacts",
    "psychologyfacts", "mindblowingtiktok", "factcheck", "amazingfacts",
    "historyfacts", "lifehacks",
]

MAX_COMMENTS = 8


def run(max_comments: int = MAX_COMMENTS) -> None:
    """Scroll the FYP and leave genuine comments on videos."""
    commented = _load_log()
    print(f"[commenter] {len(commented)} videos already commented on.", flush=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        headless = os.environ.get("TIKTOK_HEADLESS", "0") == "1"
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
            ignore_default_args=["--enable-automation"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        # Load cookies
        if not os.path.exists(COOKIES_FILE):
            print("[commenter] No cookie file — run uploader first to log in.", flush=True)
            browser.close()
            return

        with open(COOKIES_FILE) as f:
            raw = json.load(f)
        pw_cookies = [
            {
                "name": c["name"], "value": c["value"],
                "domain": c.get("domain", ".tiktok.com"),
                "path": c.get("path", "/"),
                "secure": c.get("secure", True),
                "httpOnly": c.get("httpOnly", False),
                "sameSite": "None",
            }
            for c in raw
        ]
        context.add_cookies(pw_cookies)
        page = context.new_page()

        # Warm up on FYP first (looks natural), then browse hashtag pages
        print("[commenter] Warming up on FYP...", flush=True)
        page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(20)
        page.reload(wait_until="domcontentloaded", timeout=30000)
        time.sleep(20)

        if "login" in page.url.lower():
            print("[commenter] Cookies expired — re-export from Chrome.", flush=True)
            browser.close()
            return

        # Scroll FYP a bit before moving to hashtags
        for _ in range(random.randint(2, 4)):
            page.mouse.wheel(0, 1500)
            time.sleep(random.uniform(2, 4))

        count = 0
        hashtags = random.sample(HASHTAGS, len(HASHTAGS))

        for tag in hashtags:
            if count >= max_comments:
                break

            print(f"[commenter] Browsing #{tag}...", flush=True)
            videos = _get_videos_from_tag(page, tag, already_seen=commented)
            print(f"[commenter] #{tag}: {len(videos)} new videos found", flush=True)

            for video in videos:
                if count >= max_comments:
                    break

                comment = _generate_comment(video["description"])
                if not comment:
                    continue

                success = _post_comment(page, video["url"], comment)
                if success:
                    count += 1
                    commented.add(video["url"])
                    _save_log(commented)
                    print(f"[commenter] ({count}/{max_comments}) commented on {video['url']}", flush=True)
                    print(f"  └─ \"{comment}\"", flush=True)

                    delay = random.randint(45, 120)
                    print(f"[commenter] Waiting {delay}s...", flush=True)
                    time.sleep(delay)

        browser.close()
    print(f"[commenter] Done — {count} comments posted.", flush=True)


def _get_videos_from_fyp(page, already_seen: set) -> list[dict]:
    """Scrape video URLs + descriptions from the current page."""
    try:
        videos = page.evaluate("""
            () => {
                const items = [];
                const seen = new Set();
                document.querySelectorAll('a[href*="/video/"]').forEach(a => {
                    const url = a.href.split('?')[0];
                    if (!url || seen.has(url)) return;
                    seen.add(url);
                    // Walk up to find the video container and get description
                    let desc = '';
                    let el = a;
                    for (let i = 0; i < 6; i++) {
                        el = el.parentElement;
                        if (!el) break;
                        const d = el.querySelector('[data-e2e="video-desc"], [data-e2e="search-card-desc"]');
                        if (d) { desc = d.innerText.trim(); break; }
                    }
                    items.push({ url, description: desc.slice(0, 300) });
                });
                return items;
            }
        """)
        return [v for v in (videos or []) if v["url"] not in already_seen]
    except Exception as e:
        print(f"[commenter] FYP scrape error: {e}", flush=True)
        return []


def _get_videos_from_tag(page, tag: str, already_seen: set) -> list[dict]:
    """Navigate to a hashtag page and collect video URLs + descriptions."""
    try:
        page.goto(f"https://www.tiktok.com/tag/{tag}", wait_until="domcontentloaded", timeout=25000)
        time.sleep(random.uniform(3, 5))

        # Scroll to load more videos
        for _ in range(2):
            page.mouse.wheel(0, 1500)
            time.sleep(1.5)

        # Extract video links and descriptions
        videos = page.evaluate("""
            () => {
                const items = [];
                document.querySelectorAll('a[href*="/video/"]').forEach(a => {
                    const url = a.href;
                    const desc = (
                        a.querySelector('[data-e2e="video-desc"]')?.innerText ||
                        a.closest('[data-e2e]')?.querySelector('p,span')?.innerText ||
                        ''
                    ).trim().slice(0, 300);
                    if (url && !items.find(i => i.url === url)) {
                        items.push({ url, description: desc });
                    }
                });
                return items.slice(0, 20);
            }
        """)
        return [v for v in (videos or []) if v["url"] not in already_seen]
    except Exception as e:
        print(f"[commenter] Error loading #{tag}: {e}", flush=True)
        return []


def _generate_comment(description: str) -> str | None:
    """Use Claude to write a funny, likeable comment."""
    try:
        client = anthropic.Anthropic()
        desc_line = f'Video description: "{description}"' if description.strip() else "No description — this is a general facts/life hack video."
        prompt = f"""You're leaving a comment on a TikTok video that will get hundreds of likes.

{desc_line}

Write ONE comment. The goal is to be the top comment — the one everyone likes because it's:
- Unexpectedly funny or witty
- A clever observation no one else would think of
- The kind of thing that makes people go "lmaooo" or "why is this so accurate"
- Sounds like a real person, not a bot

Rules:
- Max 120 characters
- 1 emoji max, only if it makes it funnier
- Never generic ("great video", "so true", "love this")
- Never say you don't have enough info — always write something
- Never promote yourself

Examples of the vibe:
- "my brain just quietly filed for bankruptcy"
- "bro really said 847 years like we were supposed to know that"
- "the way i immediately looked at my hands after watching this"
- "my ancestors are somewhere crying rn"

Return ONLY the comment. Nothing else."""

        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip().strip('"')
    except Exception as e:
        print(f"[commenter] Comment generation error: {e}", flush=True)
        return None


def _load_video_page(page, url: str) -> bool:
    """Navigate to a video page with wait + refresh pattern."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(20)
        page.reload(wait_until="domcontentloaded", timeout=30000)
        time.sleep(20)
        # Close any notification panels
        page.keyboard.press("Escape")
        time.sleep(1)
        return True
    except Exception as e:
        print(f"[commenter] Load error: {e}", flush=True)
        return False


def _like_video(page) -> bool:
    """Like the video only if not already liked."""
    try:
        already_liked = page.evaluate("""
            () => {
                const btn = document.querySelector('[data-e2e="like-icon"]');
                if (!btn) return null;
                // TikTok marks liked state with fill color or aria-pressed
                const svg = btn.querySelector('svg');
                const pressed = btn.closest('[aria-pressed]');
                if (pressed) return pressed.getAttribute('aria-pressed') === 'true';
                // Fallback: check if the icon has a "liked" color fill
                const style = window.getComputedStyle(svg || btn);
                return style.color === 'rgb(255, 59, 59)' || style.fill === 'rgb(255, 59, 59)';
            }
        """)
        if already_liked:
            print("[commenter] Already liked, skipping.", flush=True)
            return True
        page.locator('[data-e2e="like-icon"]').first.click(timeout=5000)
        time.sleep(random.uniform(1, 2))
        print("[commenter] Liked.", flush=True)
        return True
    except Exception:
        return False


def _post_comment(page, video_url: str, comment: str) -> bool:
    """Navigate to a video, like it, then post a comment."""
    try:
        ok = _load_video_page(page, video_url)
        if not ok:
            return False

        # Like the video first (looks natural)
        _like_video(page)
        time.sleep(random.uniform(1, 2))

        # Click comment icon to open the comment panel
        try:
            page.locator('[data-e2e="comment-icon"]').first.click(timeout=5000)
            time.sleep(random.uniform(2, 3))
        except Exception as e:
            print(f"[commenter] Could not click comment icon: {e}", flush=True)
            return False

        # Find the comment input (appears after clicking comment icon)
        input_found = page.evaluate("""
            () => {
                const candidates = [
                    ...document.querySelectorAll('[data-e2e="comment-input"]'),
                    ...document.querySelectorAll('[contenteditable="plaintext-only"]'),
                    ...document.querySelectorAll('[contenteditable="true"]'),
                    ...document.querySelectorAll('div[placeholder*="comment" i]'),
                ];
                for (const el of candidates) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 5) {
                        el.click();
                        el.focus();
                        return true;
                    }
                }
                return false;
            }
        """)

        if not input_found:
            print(f"[commenter] Comment input not found after clicking icon", flush=True)
            return False

        time.sleep(random.uniform(0.8, 1.2))

        # Type with human-like speed
        for char in comment:
            page.keyboard.type(char)
            time.sleep(random.uniform(0.04, 0.12))

        time.sleep(random.uniform(0.8, 1.2))
        page.keyboard.press("Enter")
        time.sleep(3)
        return True

    except Exception as e:
        print(f"[commenter] Error on {video_url}: {e}", flush=True)
        return False


def _load_log() -> set:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    if not os.path.exists(LOG_FILE):
        return set()
    with open(LOG_FILE) as f:
        return set(json.load(f))


def _save_log(commented: set) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "w") as f:
        json.dump(list(commented), f)
