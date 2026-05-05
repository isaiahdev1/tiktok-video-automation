"""
Test: open one YouTube Short and attempt to post a comment.
Prints exactly what happens at each step.
"""
import json, time, random
from playwright.sync_api import sync_playwright

COOKIES_FILE = "youtube_cookies.json"

_ss_map = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "none": "None"}

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
        exp = c.get("expires") or c.get("expirationDate")
        if exp and exp > 0:
            cookie["expires"] = int(exp)
        if c.get("partitionKey"):
            continue
        pw_cookies.append(cookie)
    context.add_cookies(pw_cookies)

    page = context.new_page()

    print("Loading YouTube Shorts...", flush=True)
    page.goto("https://www.youtube.com/shorts/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(8)

    print(f"URL: {page.url}", flush=True)

    # Check login
    logged_in = page.evaluate("""
        () => !!document.querySelector('button#avatar-btn, ytd-topbar-menu-button-renderer #avatar-btn')
    """)
    print(f"Logged in: {logged_in}", flush=True)

    # Click play
    page.evaluate("""
        () => {
            const btn = document.querySelector('button[aria-label="Play"], .ytp-play-button');
            if (btn) { btn.click(); return; }
            const video = document.querySelector('video');
            if (video) video.play();
        }
    """)
    time.sleep(2)

    # Scan what's on screen
    print("\n--- Visible buttons/interactive elements ---", flush=True)
    els = page.evaluate("""
        () => [...document.querySelectorAll('button, [role="button"], yt-icon-button')]
            .map(el => {
                const r = el.getBoundingClientRect();
                const label = el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText?.trim()?.slice(0,30) || '';
                return { label, w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y) };
            })
            .filter(e => e.w > 0 && e.label)
            .slice(0, 25)
    """)
    for el in els:
        print(f"  [{el['label']}] {el['w']}x{el['h']} at ({el['x']},{el['y']})", flush=True)

    # Try opening comments
    print("\nLooking for comment button...", flush=True)
    clicked = page.evaluate("""
        () => {
            for (const el of document.querySelectorAll('button, [role="button"], yt-icon-button')) {
                const label = (el.getAttribute('aria-label') || el.innerText || '').toLowerCase();
                if (label.includes('comment')) { el.click(); return label; }
            }
            return null;
        }
    """)
    print(f"Comment button clicked: {clicked}", flush=True)
    time.sleep(4)

    # Look for comment input
    print("\n--- Comment input scan ---", flush=True)
    inputs = page.evaluate("""
        () => [...document.querySelectorAll('[contenteditable], input, textarea, #simplebox-placeholder, #contenteditable-root')]
            .map(el => {
                const r = el.getBoundingClientRect();
                return { tag: el.tagName, id: el.id, ce: el.getAttribute('contenteditable'), ph: el.getAttribute('placeholder') || el.innerText?.slice(0,30) || '', w: Math.round(r.width), h: Math.round(r.height) };
            })
            .filter(e => e.w > 30)
    """)
    for el in inputs:
        print(f"  {el['tag']}#{el['id']} contenteditable={el['ce']} text='{el['ph']}' {el['w']}x{el['h']}", flush=True)

    # Try clicking the placeholder then type
    print("\nAttempting to type test comment...", flush=True)
    try:
        page.locator('#simplebox-placeholder').first.click(timeout=3000)
        time.sleep(1)
    except Exception as e:
        print(f"  simplebox-placeholder click failed: {e}", flush=True)

    focused = page.evaluate("""
        () => {
            const box = document.querySelector('#contenteditable-root, [contenteditable="true"]');
            if (box) { const r = box.getBoundingClientRect(); if (r.width > 50) { box.click(); box.focus(); return true; } }
            return false;
        }
    """)
    print(f"Input focused: {focused}", flush=True)

    if focused:
        test_comment = "test comment — ignore this"
        for char in test_comment:
            page.keyboard.type(char)
            time.sleep(0.05)
        time.sleep(1)

        print("\n--- Submit button scan ---", flush=True)
        btns = page.evaluate("""
            () => [...document.querySelectorAll('button, yt-button-shape')]
                .map(el => {
                    const r = el.getBoundingClientRect();
                    return { tag: el.tagName, id: el.id, label: el.getAttribute('aria-label') || el.innerText?.trim()?.slice(0,20) || '', w: Math.round(r.width), h: Math.round(r.height) };
                })
                .filter(e => e.w > 0 && e.label)
                .slice(0, 20)
        """)
        for b in btns:
            print(f"  {b['tag']}#{b['id']} [{b['label']}] {b['w']}x{b['h']}", flush=True)

        print("\nClicking submit button...", flush=True)
        submit = page.evaluate("""
            () => {
                const selectors = [
                    '#submit-button yt-button-shape button',
                    '#submit-button button',
                    'ytd-comment-simplebox-renderer #submit-button button',
                    'button[aria-label="Comment"]',
                ];
                for (const sel of selectors) {
                    const btn = document.querySelector(sel);
                    if (btn) {
                        const r = btn.getBoundingClientRect();
                        if (r.width > 0) { btn.click(); return 'clicked: ' + sel; }
                    }
                }
                return 'not found';
            }
        """)
        print(f"Submit result: {submit}", flush=True)
        time.sleep(3)
        print("Done — check if comment appeared on the video.", flush=True)

    print("\nKeeping browser open 20s — check what's on screen...", flush=True)
    time.sleep(20)
    browser.close()
    print("Done.", flush=True)
