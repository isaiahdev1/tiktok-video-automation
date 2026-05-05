"""
Run this once to log into YouTube and save cookies.
Usage: venv/bin/python capture_youtube_cookies.py
"""
import json, time
from playwright.sync_api import sync_playwright

COOKIES_FILE = "youtube_cookies.json"

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
    page = context.new_page()
    page.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=30000)

    print("Sign into YouTube in the browser window.", flush=True)
    print("Waiting for login (up to 3 minutes)...", flush=True)

    try:
        page.wait_for_selector("button#avatar-btn", timeout=180000)
        print("Logged in! Saving cookies...", flush=True)
        time.sleep(3)
        cookies = context.cookies()
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"Saved {len(cookies)} cookies to {COOKIES_FILE}", flush=True)
    except Exception as e:
        print(f"Timed out waiting for login: {e}", flush=True)

    browser.close()
