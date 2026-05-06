"""
FYP commenter — likes and comments on videos directly from the For You page.
No page navigation. Scrolls through the feed naturally.
"""

from __future__ import annotations
import json
import os
import random
import time
import anthropic

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "..", "tiktok_cookies.json")
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "output", "comment_log.json")
MAX_COMMENTS = 8


def run(max_comments: int = MAX_COMMENTS) -> None:
    commented = _load_log()
    print(f"[fyp] {len(commented)} videos already commented on.", flush=True)

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
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        if not os.path.exists(COOKIES_FILE):
            print("[fyp] No cookie file found.", flush=True)
            browser.close()
            return

        with open(COOKIES_FILE) as f:
            raw = json.load(f)
        context.add_cookies([{
            "name": c["name"], "value": c["value"],
            "domain": c.get("domain", ".tiktok.com"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": "None",
        } for c in raw])

        page = context.new_page()

        # Load FYP with wait + refresh
        print("[fyp] Loading FYP...", flush=True)
        page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(20)
        page.reload(wait_until="domcontentloaded", timeout=30000)
        time.sleep(20)
        page.keyboard.press("Escape")
        time.sleep(1)

        if "login" in page.url.lower():
            print("[fyp] Cookies expired.", flush=True)
            browser.close()
            return

        count = 0
        videos_since_last_comment = 0
        # Irregular gaps: sometimes 2, sometimes 7 — feels human, not patterned
        next_comment_after = random.choice([1, 2, 3, 4, 5, 6, 7, 8])

        while count < max_comments:
            # Get current video info
            desc = page.evaluate("""
                () => document.querySelectorAll('[data-e2e="video-desc"]')[0]?.innerText?.trim() || ''
            """)
            video_id = page.evaluate("""
                () => document.querySelectorAll('a[href*="/video/"]')[0]?.href?.split('?')[0] || ''
            """)
            unique_key = video_id or desc[:80]

            # Watch the video — vary widely (quick scroll vs. actually watching)
            watch_time = random.uniform(3, 22)
            time.sleep(watch_time)

            # Decide whether to comment on this video
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
                        print(f"[fyp] ({count}/{max_comments}) └─ \"{comment}\"", flush=True)

                        # Doom scroll 2-5 videos after commenting, linger on each
                        post_scrolls = random.choice([2, 2, 3, 3, 4, 5])
                        print(f"[fyp] Scrolling {post_scrolls} videos after comment...", flush=True)
                        for _ in range(post_scrolls):
                            time.sleep(random.uniform(4, 20))
                            _scroll_to_next(page)
                            videos_since_last_comment += 1

                        # Brief pause before resuming
                        time.sleep(random.uniform(2, 6))

                        # Pick a new unpredictable gap before next comment
                        videos_since_last_comment = 0
                        next_comment_after = random.choice([2, 3, 3, 4, 4, 5, 6, 7])
            elif unique_key in commented:
                pass  # already seen, just scroll past

            _scroll_to_next(page)
            videos_since_last_comment += 1

        browser.close()
    print(f"[fyp] Done — {count} comments posted.", flush=True)


def _like(page) -> None:
    """Like the current video after UI has fully settled."""
    try:
        # Move mouse away from comment area first
        page.mouse.move(200, 450)
        time.sleep(3)  # wait for all animations/panels to fully settle

        page.locator('[data-e2e="like-icon"]').first.click(timeout=5000)
        time.sleep(1.5)
        print("[fyp] Liked.", flush=True)
    except Exception as e:
        print(f"[fyp] Like error: {e}", flush=True)


def _comment(page, text: str) -> bool:
    """Click comment icon, type comment, submit."""
    try:
        # Open comment sidebar
        page.locator('[data-e2e="comment-icon"]').first.click(timeout=5000)

        # Poll up to 8s for the input to appear
        found = False
        for _ in range(16):
            time.sleep(0.5)
            try:
                page.locator('[data-e2e="comment-input"]').first.click(timeout=500)
            except Exception:
                pass
            found = page.evaluate("""
                () => {
                    const box = document.querySelector('[data-e2e="comment-input"] [contenteditable]')
                             || document.querySelector('[contenteditable="plaintext-only"]')
                             || document.querySelector('[contenteditable="true"]');
                    if (box) { const r = box.getBoundingClientRect(); if (r.width > 50) { box.click(); box.focus(); return true; } }
                    return false;
                }
            """)
            if found:
                break

        if not found:
            print("[fyp] Comment input not found.", flush=True)
            page.keyboard.press("Escape")
            return False

        time.sleep(random.uniform(0.5, 1))

        # Type with human-like speed
        for char in text:
            page.keyboard.type(char)
            time.sleep(random.uniform(0.04, 0.12))

        time.sleep(random.uniform(0.8, 1.2))
        page.keyboard.press("Enter")
        time.sleep(2.5)

        # Close sidebar
        page.keyboard.press("Escape")
        time.sleep(1)
        return True

    except Exception as e:
        print(f"[fyp] Comment error: {e}", flush=True)
        page.keyboard.press("Escape")
        return False


def _scroll_to_next(page) -> None:
    """Advance to the next video, trying multiple methods until one works."""
    before_id = page.evaluate(
        "() => document.querySelectorAll('a[href*=\"/video/\"]')[0]?.href?.split('?')[0] || ''"
    )
    before_desc = page.evaluate(
        "() => document.querySelectorAll('[data-e2e=\"video-desc\"]')[0]?.innerText?.trim()?.slice(0,40) || ''"
    )

    def _changed() -> bool:
        after_id = page.evaluate(
            "() => document.querySelectorAll('a[href*=\"/video/\"]')[0]?.href?.split('?')[0] || ''"
        )
        after_desc = page.evaluate(
            "() => document.querySelectorAll('[data-e2e=\"video-desc\"]')[0]?.innerText?.trim()?.slice(0,40) || ''"
        )
        return (after_id and after_id != before_id) or (after_desc and after_desc != before_desc)

    for attempt in range(4):
        if attempt == 0:
            # Method 1: click TikTok's own down-arrow nav button
            try:
                btn = page.locator('[data-e2e="arrow-down"], [class*="ButtonBasic"][aria-label*="next" i], [class*="arrow-down"]').first
                btn.click(timeout=2000)
            except Exception:
                page.mouse.wheel(0, 900)
        elif attempt == 1:
            # Method 2: mouse wheel on the feed container
            page.mouse.wheel(0, 900)
        elif attempt == 2:
            # Method 3: ArrowDown with explicit focus on body
            page.evaluate("document.body.focus()")
            page.keyboard.press("ArrowDown")
        else:
            # Method 4: JS scroll the feed container directly
            page.evaluate("""
                () => {
                    const feed = document.querySelector('[class*="DivVideoFeedV2"], [data-e2e="recommend-list-item-container"], main');
                    if (feed) feed.scrollBy(0, window.innerHeight);
                    else window.scrollBy(0, window.innerHeight);
                }
            """)

        time.sleep(random.uniform(2.5, 3.5))
        if _changed():
            return

        if attempt < 3:
            print(f"[fyp] Scroll method {attempt+1} didn't advance, trying next...", flush=True)


def _generate_comment(description: str) -> str | None:
    try:
        client = anthropic.Anthropic()
        desc_line = f'Video: "{description}"' if description.strip() else "General facts/entertainment video."
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": f"""Leave a TikTok comment that will get likes.

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
        print(f"[fyp] Comment gen error: {e}", flush=True)
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
