"""
Quick test: open one TikTok video, read comments, try to click the input box.
"""
import json, os, time
from dotenv import load_dotenv
load_dotenv()

COOKIES_FILE = "tiktok_cookies.json"
TEST_URL = "https://www.tiktok.com/tag/didyouknow"  # hashtag page first to find a live video

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
    print("Opening page...", flush=True)
    page.goto(TEST_URL, wait_until="domcontentloaded", timeout=30000)
    print("Waiting 20s for page to settle...", flush=True)
    time.sleep(20)

    print("Refreshing...", flush=True)
    page.reload(wait_until="domcontentloaded", timeout=30000)
    print("Waiting another 20s after refresh...", flush=True)
    time.sleep(20)

    print(f"Page title: {page.title()}", flush=True)
    print(f"Current URL: {page.url}", flush=True)

    # Dump all hrefs to see what TikTok actually renders
    all_links = page.evaluate("""
        () => [...document.querySelectorAll('a[href]')]
            .map(a => a.href)
            .filter(h => h.includes('tiktok.com'))
            .slice(0, 30)
    """)
    print(f"All TikTok links on page ({len(all_links)}):", flush=True)
    for l in all_links:
        print(f"  {l}", flush=True)

    video_url = next((l.split('?')[0] for l in all_links if '/video/' in l), None)
    print(f"\nFirst video found: {video_url}", flush=True)

    if video_url:
        print("\nNavigating to video...", flush=True)
        page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
        print("Waiting 45s...", flush=True)
        time.sleep(45)
        print("Refreshing video page...", flush=True)
        page.reload(wait_until="domcontentloaded", timeout=30000)
        print("Waiting another 45s...", flush=True)
        time.sleep(45)

        print(f"Video page title: {page.title()}", flush=True)

        # Close any open panels (inbox etc)
        page.keyboard.press("Escape")
        time.sleep(1)

        # Scan for video-specific elements
        print("\n--- Video page elements (data-e2e) ---", flush=True)
        found = page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('[data-e2e]').forEach(el => {
                    const e2e = el.getAttribute('data-e2e');
                    if (e2e && (
                        e2e.includes('like') || e2e.includes('comment') ||
                        e2e.includes('browse') || e2e.includes('video') ||
                        e2e.includes('share') || e2e.includes('input')
                    )) {
                        const rect = el.getBoundingClientRect();
                        results.push({
                            tag: el.tagName,
                            e2e: e2e,
                            contenteditable: el.getAttribute('contenteditable'),
                            placeholder: el.getAttribute('placeholder') || '',
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        });
                    }
                });
                return results.slice(0, 30);
            }
        """)
        for el in found:
            print(f"  {el['tag']} e2e='{el['e2e']}' contenteditable={el['contenteditable']} placeholder='{el['placeholder']}' {el['width']}x{el['height']}", flush=True)
        if not found:
            print("  (none found — inbox may still be open)", flush=True)

    print("\nKeeping browser open 20s — look at what's on screen...", flush=True)
    time.sleep(20)
    browser.close()
    print("Done.", flush=True)
