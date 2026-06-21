"""Upload videos to TikTok via Playwright browser automation."""

from __future__ import annotations
import os
import time

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "..", "tiktok_profile")
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "..", "tiktok_cookies.json")
UPLOAD_URL = "https://www.tiktok.com/upload"


def upload_to_tiktok(video_path: str, caption: str, tags: list[str]) -> bool:
    """Attempt the TikTok upload up to twice; return True only if confirmed."""
    for attempt in range(1, 3):
        print(f"[tiktok] Upload attempt {attempt}/2...")
        try:
            if _attempt_upload(video_path, caption, tags):
                return True
        except Exception as e:
            print(f"[tiktok] Attempt {attempt} errored: {e}")
        if attempt < 2:
            print("[tiktok] Retrying in 15s...")
            time.sleep(15)
    print("[tiktok] All attempts failed.")
    return False


def _attempt_upload(video_path: str, caption: str, tags: list[str]) -> bool:
    """
    Upload a video to TikTok using a persistent browser profile.

    First run: opens a visible browser — log into TikTok, then the script
    continues automatically. Login is saved in tiktok_profile/ forever.

    Returns True on success.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

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

        # ── Inject cookies from Cookie-Editor export ─────────────────
        cookies_path = os.path.abspath(COOKIES_FILE)
        if os.path.exists(cookies_path):
            import json
            with open(cookies_path) as f:
                raw = json.load(f)
            # Cookie-Editor format → Playwright format
            pw_cookies = []
            for c in raw:
                pw_cookies.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".tiktok.com"),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", True),
                    "httpOnly": c.get("httpOnly", False),
                    "sameSite": "None",
                })
            context.add_cookies(pw_cookies)
            print(f"[tiktok] Loaded {len(pw_cookies)} cookies.")
        else:
            print(f"[tiktok] No cookie file found at {cookies_path}")
            print("[tiktok] See instructions for exporting cookies from Chrome.")
            context.close()
            browser.close()
            return False

        page = context.new_page()
        page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        if "login" in page.url:
            print("[tiktok] Cookies didn't work — they may have expired. Re-export from Chrome.")
            context.close()
            browser.close()
            return False

        # ── File upload ──────────────────────────────────────────────
        print("[tiktok] Attaching video...")
        try:
            # Upload input may be inside an iframe
            target = page
            for frame in page.frames:
                if "upload" in (frame.url or ""):
                    target = frame
                    break

            file_input = target.locator("input[type='file']").first
            file_input.set_input_files(os.path.abspath(video_path))
        except Exception as e:
            print(f"[tiktok] Could not attach file: {e}")
            context.close()
            return False

        # ── Wait for TikTok to finish reviewing the video ───────────
        # Headless uploads in CI can take a while to finish processing. We
        # wait up to ~4 min and treat the Post button as ready only when it
        # is truly enabled (TikTok marks it disabled via the `disabled`
        # property, `aria-disabled`, OR a CSS class while processing).
        print("[tiktok] Waiting for TikTok to finish reviewing video...")
        ready = False
        for i in range(120):  # wait up to ~240 seconds
            time.sleep(2)
            try:
                ready = page.evaluate("""
                    () => {
                        const btns = [...document.querySelectorAll('button')];
                        const post = btns.find(b => b.innerText.trim() === 'Post');
                        if (!post) return false;
                        const aria = post.getAttribute('aria-disabled');
                        const cls = (post.className || '').toLowerCase();
                        const looksDisabled =
                            post.disabled ||
                            aria === 'true' ||
                            cls.includes('disabled');
                        return !looksDisabled;
                    }
                """)
                if ready:
                    print(f"[tiktok] Video ready after {(i+1)*2}s.")
                    break
            except Exception:
                pass

        if not ready:
            # Don't fire a broken "post anyway" — that creates empty/failed
            # posts and false success. Bail so the run can retry cleanly.
            print("[tiktok] Post never became ready — aborting this attempt.")
            browser.close()
            return False

        # ── Set caption via JavaScript (bypasses React modal issues) ─
        tag_str = " ".join(f"#{t.replace(' ', '')}" for t in tags[:5])
        full_caption = f"{caption} {tag_str}"[:150]
        try:
            page.evaluate(f"""
                const box = document.querySelector('[data-text="true"]');
                if (box) {{
                    box.focus();
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertText', false, {repr(full_caption)});
                }}
            """)
            time.sleep(1)
            print("[tiktok] Caption set.")
        except Exception as e:
            print(f"[tiktok] Caption set failed (non-fatal): {e}")

        # ── Click Post via JavaScript ────────────────────────────────
        try:
            page.evaluate("""
                const btns = [...document.querySelectorAll('button')];
                const post = btns.find(b => b.innerText.trim() === 'Post');
                if (post) post.click();
            """)
            print("[tiktok] Post clicked.")
        except Exception as e:
            print(f"[tiktok] Post click failed: {e}")
            browser.close()
            return False

        # ── Verify the post actually landed ──────────────────────────
        # On success TikTok redirects away from /upload to the content
        # manager and/or shows a "your video is being uploaded" toast.
        # We only report success if we observe one of those signals —
        # never a blind "assume it worked".
        print("[tiktok] Verifying post...")
        posted = False
        for _ in range(30):  # up to ~60s
            time.sleep(2)
            try:
                url = page.url or ""
                if "upload" not in url:
                    print(f"[tiktok] Confirmed — redirected to {url}")
                    posted = True
                    break
                seen_toast = page.evaluate("""
                    () => {
                        const t = document.body.innerText.toLowerCase();
                        return t.includes('your video is being uploaded')
                            || t.includes('your videos')
                            || t.includes('manage your posts')
                            || t.includes('view profile');
                    }
                """)
                if seen_toast:
                    print("[tiktok] Confirmed — success toast detected.")
                    posted = True
                    break
            except Exception:
                pass

        browser.close()
        if posted:
            print("[tiktok] Upload confirmed.")
        else:
            print("[tiktok] Could NOT confirm the post landed — treating as FAILED.")
        return posted
