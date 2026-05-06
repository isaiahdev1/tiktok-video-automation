"""
FYP commenter — loads the For You page, scrolls to populate the DOM with
real FYP videos, scrapes their URLs, then navigates to each one to like
and comment. Same viral content a normal person would see on the FYP.
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

        # ── Load FYP ─────────────────────────────────────────────────
        print("[fyp] Loading For You page...", flush=True)
        page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded", timeout=30000)
        time.sleep(8)
        page.keyboard.press("Escape")
        time.sleep(1)

        if "login" in page.url.lower():
            print("[fyp] Cookies expired — re-export from Chrome.", flush=True)
            browser.close()
            return

        # ── Scroll to populate DOM with FYP videos ───────────────────
        print("[fyp] Scrolling FYP to load videos...", flush=True)
        for _ in range(6):
            page.mouse.wheel(0, 1200)
            time.sleep(1.5)

        # ── Scrape all video URLs now in the DOM ─────────────────────
        videos = page.evaluate("""
            () => {
                const seen = new Set();
                const items = [];
                document.querySelectorAll('a[href*="/video/"]').forEach(a => {
                    const url = a.href.split('?')[0];
                    if (!url || seen.has(url)) return;
                    seen.add(url);
                    let desc = '';
                    let el = a;
                    for (let i = 0; i < 8; i++) {
                        el = el.parentElement;
                        if (!el) break;
                        const d = el.querySelector('[data-e2e="video-desc"], p');
                        if (d) { desc = d.innerText.trim(); break; }
                    }
                    items.push({ url, description: desc.slice(0, 300) });
                });
                return items;
            }
        """)

        fresh = [v for v in (videos or []) if v["url"] not in commented]
        random.shuffle(fresh)
        print(f"[fyp] {len(fresh)} fresh FYP videos ready.", flush=True)

        if not fresh:
            print("[fyp] No new FYP videos — cookies may have expired.", flush=True)
            browser.close()
            return

        # ── Navigate to each video and comment ───────────────────────
        count = 0
        for video in fresh:
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
                print(f"[fyp] ({count}/{max_comments}) {video['url']}", flush=True)
                print(f'  └─ "{comment}"', flush=True)

                if count < max_comments:
                    delay = random.randint(45, 90)
                    print(f"[fyp] Waiting {delay}s...", flush=True)
                    time.sleep(delay)

        browser.close()
    print(f"[fyp] Done — {count} comments posted.", flush=True)


def _post_comment(page, video_url: str, comment: str) -> bool:
    try:
        page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(8)
        page.keyboard.press("Escape")
        time.sleep(1)

        # Like the video
        try:
            already_liked = page.evaluate("""
                () => {
                    const btn = document.querySelector('[data-e2e="like-icon"]');
                    if (!btn) return false;
                    const pressed = btn.closest('[aria-pressed]');
                    return pressed ? pressed.getAttribute('aria-pressed') === 'true' : false;
                }
            """)
            if not already_liked:
                page.locator('[data-e2e="like-icon"]').first.click(timeout=5000)
                time.sleep(random.uniform(1, 2))
                print("[fyp] Liked.", flush=True)
        except Exception:
            pass

        # Open comment panel
        page.locator('[data-e2e="comment-icon"]').first.click(timeout=5000)
        time.sleep(random.uniform(2, 3))

        # Find and focus comment input
        input_found = False
        for _ in range(16):
            time.sleep(0.5)
            input_found = page.evaluate("""
                () => {
                    const candidates = [
                        ...document.querySelectorAll('[data-e2e="comment-input"] [contenteditable]'),
                        ...document.querySelectorAll('[contenteditable="plaintext-only"]'),
                        ...document.querySelectorAll('[contenteditable="true"]'),
                    ];
                    for (const el of candidates) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 50 && r.height > 5) {
                            el.click();
                            el.focus();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if input_found:
                break

        if not input_found:
            print(f"[fyp] Comment input not found.", flush=True)
            return False

        time.sleep(random.uniform(0.5, 1))

        for char in comment:
            page.keyboard.type(char)
            time.sleep(random.uniform(0.04, 0.12))

        time.sleep(random.uniform(0.8, 1.2))
        page.keyboard.press("Enter")
        time.sleep(3)
        return True

    except Exception as e:
        print(f"[fyp] Error on {video_url}: {e}", flush=True)
        return False


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
