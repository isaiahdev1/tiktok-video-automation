"""
YouTube Shorts FYP commenter — doom scrolls Shorts feed and leaves AI comments.
Mirrors the TikTok FYP commenter behavior: unpredictable gaps, variable watch time.
"""

from __future__ import annotations
import json
import os
import random
import time
import anthropic

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "..", "youtube_cookies.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "output", "yt_comment_log.json")
MAX_COMMENTS = 8


def run(max_comments: int = MAX_COMMENTS) -> None:
    commented = _load_log()
    print(f"[yt] {len(commented)} videos already commented on.", flush=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE) as f:
                raw = json.load(f)
            _ss_map = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "none": "None"}
            pw_cookies = []
            for c in raw:
                ss_raw = (c.get("sameSite") or "").lower()
                cookie = {
                    "name": c["name"], "value": c["value"],
                    "domain": c.get("domain", ".youtube.com"),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", True),
                    "httpOnly": c.get("httpOnly", False),
                    "sameSite": _ss_map.get(ss_raw, "None"),
                }
                # Playwright uses 'expires', Chrome exports use 'expirationDate'
                exp = c.get("expires") or c.get("expirationDate")
                if exp and exp > 0:
                    cookie["expires"] = int(exp)
                # Skip partition-keyed cookies — Playwright doesn't support them
                if c.get("partitionKey"):
                    continue
                pw_cookies.append(cookie)
            context.add_cookies(pw_cookies)

        page = context.new_page()

        # Navigate to Shorts
        print("[yt] Loading Shorts feed...", flush=True)
        page.goto("https://www.youtube.com/shorts/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(10)
        page.reload(wait_until="domcontentloaded", timeout=30000)
        time.sleep(10)
        page.keyboard.press("Escape")
        time.sleep(1)

        # Click play button if video is paused on load
        page.evaluate("""
            () => {
                const btn = document.querySelector(
                    'button[aria-label="Play"], button[title="Play"], .ytp-play-button'
                );
                if (btn) { btn.click(); return; }
                // Fallback: click center of video player
                const video = document.querySelector('video');
                if (video) { video.play(); }
            }
        """)
        time.sleep(2)
        print("[yt] Play triggered.", flush=True)

        count = 0
        videos_since_last_comment = 0
        next_comment_after = random.choice([1, 2, 3, 4, 5, 6, 7, 8])

        while count < max_comments:
            # Get current video ID from URL
            video_id = page.evaluate("""
                () => { const m = location.href.match(/shorts\\/([a-zA-Z0-9_-]{8,})/); return m ? m[1] : ''; }
            """)
            desc = page.evaluate("""
                () => {
                    const h2 = document.querySelector('h2')?.innerText?.trim() || '';
                    const title = document.title.replace(' - YouTube', '').trim();
                    const channel = document.querySelector('ytd-reel-player-overlay-renderer')
                        ?.innerText?.split('\\n')[0]?.trim() || '';
                    return (h2 || title || channel).slice(0, 300);
                }
            """)
            unique_key = video_id or desc[:80]

            # Watch for a natural amount of time
            watch_time = random.uniform(3, 22)
            time.sleep(watch_time)

            should_comment = videos_since_last_comment >= next_comment_after

            if should_comment and unique_key not in commented:
                if unique_key:
                    commented.add(unique_key)

                comment = _generate_comment(desc)
                if comment:
                    success = _comment(page, comment)
                    if success:
                        count += 1
                        _save_log(commented)
                        print(f"[yt] ({count}/{max_comments}) └─ \"{comment}\"", flush=True)

                        # Doom scroll 2-5 videos after commenting
                        post_scrolls = random.choice([2, 2, 3, 3, 4, 5])
                        print(f"[yt] Scrolling {post_scrolls} videos after comment...", flush=True)
                        for _ in range(post_scrolls):
                            time.sleep(random.uniform(4, 20))
                            _scroll_to_next(page)
                            videos_since_last_comment += 1

                        time.sleep(random.uniform(2, 6))
                        videos_since_last_comment = 0
                        next_comment_after = random.choice([2, 3, 3, 4, 4, 5, 6, 7])
            elif unique_key in commented:
                pass

            _scroll_to_next(page)
            videos_since_last_comment += 1

        browser.close()
    print(f"[yt] Done — {count} comments posted.", flush=True)


def _comment(page, text: str) -> bool:
    """Open comment panel, type comment, submit."""
    try:
        # Click the comments button (label is "View N comments")
        clicked = page.evaluate("""
            () => {
                for (const btn of document.querySelectorAll('button, [role="button"]')) {
                    const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                    if (label.includes('comment')) { btn.click(); return label; }
                }
                return null;
            }
        """)

        if not clicked:
            print("[yt] Comment button not found by label, trying position...", flush=True)
            page.mouse.click(866, 586)

        # Poll up to 10s for the comment input
        found = False
        for _ in range(20):
            time.sleep(0.5)
            # Try clicking the placeholder text first
            try:
                page.locator('#simplebox-placeholder').first.click(timeout=300)
                time.sleep(0.5)
            except Exception:
                pass

            found = page.evaluate("""
                () => {
                    const box = document.querySelector(
                        '#contenteditable-root, '
                        + '[contenteditable="true"], '
                        + '[contenteditable="plaintext-only"]'
                    );
                    if (box) {
                        const r = box.getBoundingClientRect();
                        if (r.width > 50) { box.click(); box.focus(); return true; }
                    }
                    return false;
                }
            """)
            if found:
                break

        if not found:
            print("[yt] Comment input not found.", flush=True)
            page.keyboard.press("Escape")
            return False

        print("[yt] Comment input found, typing...", flush=True)
        time.sleep(random.uniform(0.5, 1))

        # Type with human-like speed
        for char in text:
            page.keyboard.type(char)
            time.sleep(random.uniform(0.04, 0.12))

        time.sleep(random.uniform(0.8, 1.2))

        # Submit — try every known YouTube submit button selector
        submitted = page.evaluate("""
            () => {
                const selectors = [
                    '#submit-button yt-button-shape button',
                    '#submit-button button',
                    'ytd-comment-simplebox-renderer #submit-button button',
                    'yt-button-shape[class*="submit"] button',
                    '#contenteditable-root ~ * button',
                    'button[aria-label="Comment"]',
                ];
                for (const sel of selectors) {
                    const btn = document.querySelector(sel);
                    if (btn) {
                        const r = btn.getBoundingClientRect();
                        if (r.width > 0) { btn.click(); return sel; }
                    }
                }
                return null;
            }
        """)
        if submitted:
            print(f"[yt] Submitted via: {submitted}", flush=True)
        else:
            # Last resort: Tab to submit button then Enter
            page.keyboard.press("Tab")
            time.sleep(0.3)
            page.keyboard.press("Tab")
            time.sleep(0.3)
            page.keyboard.press("Enter")
            print("[yt] Submitted via Tab+Enter fallback", flush=True)

        time.sleep(3)
        page.keyboard.press("Escape")
        time.sleep(1)
        return True

    except Exception as e:
        print(f"[yt] Comment error: {e}", flush=True)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False


def _scroll_to_next(page) -> None:
    """Advance to the next Short, verify it changed, retry if stuck."""
    before_url = page.url

    for attempt in range(3):
        # Click Next video — use direct position (confirmed at 1200,494) + label fallback
        page.mouse.click(1200, 494)
        advanced = True

        time.sleep(random.uniform(2.5, 3.5))

        if page.url != before_url:
            return

        if attempt < 2:
            print("[yt] Scroll didn't advance, retrying...", flush=True)


def _generate_comment(description: str) -> str | None:
    try:
        client = anthropic.Anthropic()
        desc_line = f'Video: "{description}"' if description.strip() else "General entertainment/viral short video."
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": f"""Leave a YouTube comment that will get likes.

{desc_line}

Write ONE short comment (max 120 chars). Make it:
- Funny, clever, or unexpectedly relatable
- Something that makes people go "lmaooo" or "why is this so accurate"
- Real person energy, not bot energy
- Never generic ("great video", "love this")
- 1 emoji max

Examples: "my brain just quietly filed for bankruptcy" / "bro said it like we were supposed to already know" / "the way i'm telling this at every party now"

Return ONLY the comment."""}],
        )
        return msg.content[0].text.strip().strip('"')
    except Exception as e:
        print(f"[yt] Comment gen error: {e}", flush=True)
        return None


def _load_log() -> set:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    if not os.path.exists(LOG_FILE):
        return set()
    with open(LOG_FILE) as f:
        return set(json.load(f))


def _save_log(commented: set) -> None:
    with open(LOG_FILE, "w") as f:
        json.dump(list(commented), f)
