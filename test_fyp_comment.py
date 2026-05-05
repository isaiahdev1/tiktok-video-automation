"""
Test: comment directly on FYP videos without navigating away.
Like + open comment sidebar + type + submit — all from the feed.
"""
import json, os, time, random
from dotenv import load_dotenv
load_dotenv()

COOKIES_FILE = "tiktok_cookies.json"

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )

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
    print("Loading FYP...", flush=True)
    page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=30000)
    print("Waiting 20s...", flush=True)
    time.sleep(20)
    print("Refreshing...", flush=True)
    page.reload(wait_until="domcontentloaded", timeout=30000)
    print("Waiting 20s...", flush=True)
    time.sleep(20)

    # Close any panels
    page.keyboard.press("Escape")
    time.sleep(1)

    # Check what video elements are visible
    print("\n--- FYP video elements ---", flush=True)
    els = page.evaluate("""
        () => [...document.querySelectorAll('[data-e2e]')]
            .filter(el => {
                const e = el.getAttribute('data-e2e');
                return e && (e.includes('like') || e.includes('comment') || e.includes('share') || e.includes('video'));
            })
            .map(el => {
                const r = el.getBoundingClientRect();
                return { tag: el.tagName, e2e: el.getAttribute('data-e2e'), w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y) };
            })
            .filter(el => el.w > 0)
            .slice(0, 20)
    """)
    for el in els:
        print(f"  {el['tag']} [{el['e2e']}] {el['w']}x{el['h']} at ({el['x']},{el['y']})", flush=True)

    # Try clicking like-icon
    print("\nTrying to like...", flush=True)
    try:
        page.locator('[data-e2e="like-icon"]').first.click(timeout=5000)
        time.sleep(2)
        print("Like clicked!", flush=True)
    except Exception as e:
        print(f"Like failed: {e}", flush=True)

    # Try clicking comment-icon to open sidebar
    print("\nTrying to open comment sidebar...", flush=True)
    try:
        page.locator('[data-e2e="comment-icon"]').first.click(timeout=5000)
        time.sleep(3)
        print("Comment icon clicked!", flush=True)
    except Exception as e:
        print(f"Comment icon failed: {e}", flush=True)

    # Scan for comment input after sidebar opens
    print("\n--- Comment input after sidebar open ---", flush=True)
    inputs = page.evaluate("""
        () => [...document.querySelectorAll('[contenteditable], input, textarea, [data-e2e*="comment-input"]')]
            .map(el => {
                const r = el.getBoundingClientRect();
                return { tag: el.tagName, e2e: el.getAttribute('data-e2e') || '', ce: el.getAttribute('contenteditable'), ph: el.getAttribute('placeholder') || '', w: Math.round(r.width), h: Math.round(r.height) };
            })
            .filter(el => el.w > 30)
    """)
    for el in inputs:
        print(f"  {el['tag']} e2e='{el['e2e']}' contenteditable={el['ce']} placeholder='{el['ph']}' {el['w']}x{el['h']}", flush=True)

    print("\nKeeping browser open 20s...", flush=True)
    time.sleep(20)
    browser.close()
    print("Done.", flush=True)
