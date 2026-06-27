#!/usr/bin/env python3
"""Authenticated dev screenshots with overlay-dismissal + optional clicks.

A more capable sibling of dev-screenshot.py for verifying multi-step flows
(e.g. Phase 2 wizard). It logs in, suppresses the daily-drop "Back Page"
modal (which auto-opens and covers the page), optionally clicks a sequence
of elements by visible text, scrolls, then captures full-page mobile +
desktop PNGs.

Usage:
    python3 frontend/scripts/dev-shot-flow.py <path> [out_prefix] \
        [--click "PHASE II"] [--click "Knockout"] [--settle 1500]

Writes /tmp/<out_prefix>_mobile.png and /tmp/<out_prefix>_desktop.png.
Dev login: test@example.com / testpass123 (dev DB only).
"""
import argparse
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
API = "http://localhost:8000"
EMAIL, PASSWORD = "test@example.com", "testpass123"


def login_token() -> str:
    req = urllib.request.Request(
        f"{API}/api/auth/login",
        data=json.dumps({"email": EMAIL, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req))["access_token"]


def dismiss_overlays(page) -> None:
    # The Back Page drop modal listens for Escape; press a couple of times in
    # case a story page is mid-transition. Harmless if no modal is open.
    for _ in range(2):
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("out_prefix", nargs="?", default="flow")
    ap.add_argument("--click", action="append", default=[],
                    help="visible text of an element to click (repeatable, in order)")
    ap.add_argument("--settle", type=int, default=1500)
    args = ap.parse_args()
    token = login_token()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, vp in [
            ("mobile", {"width": 390, "height": 1400}),
            ("desktop", {"width": 1380, "height": 2400}),
        ]:
            ctx = browser.new_context(viewport=vp)
            page = ctx.new_page()
            page.goto(f"{BASE}/login")
            page.evaluate(f"localStorage.setItem('predictor_token', '{token}')")
            # Pre-mark all drops seen so the modal never auto-opens.
            page.evaluate("localStorage.setItem('predictor_seen_drops', JSON.stringify(['__all__']))")
            page.goto(f"{BASE}{args.path}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(args.settle)
            dismiss_overlays(page)
            for text in args.click:
                try:
                    # Desktop + mobile variants of a control coexist in the DOM
                    # (CSS hides one). Click the first VISIBLE match.
                    locs = page.get_by_text(text, exact=True)
                    target = next(
                        (locs.nth(i) for i in range(locs.count()) if locs.nth(i).is_visible()),
                        None,
                    )
                    if target is None:
                        print(f"  (click '{text}': no visible match)", file=sys.stderr)
                        continue
                    target.scroll_into_view_if_needed()
                    target.click(timeout=3000)
                    page.wait_for_timeout(600)
                except Exception as e:  # noqa: BLE001
                    print(f"  (click '{text}' skipped: {e})", file=sys.stderr)
            page.wait_for_timeout(500)
            out = f"/tmp/{args.out_prefix}_{name}.png"
            page.screenshot(path=out, full_page=True)
            print(out)
            ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
