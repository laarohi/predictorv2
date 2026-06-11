#!/usr/bin/env python3
"""Screenshot a dev-server page at mobile + desktop widths, authenticated.

Visual verification step for UI changes BEFORE deploying — svelte-check
and vitest can't catch wiring bugs between data and rendering (e.g. the
heatmap axes regression of 2026-06-12).

Usage:
    python3 frontend/scripts/dev-screenshot.py /results/<fixture_id> [selector]

Writes /tmp/shot_mobile.png and /tmp/shot_desktop.png — full page when no
selector is given, else the first VISIBLE element matching it.

Requires: the dev stack up (frontend-dev :5173 + backend :8000), Python
playwright (chromium), and the dev login test@example.com / testpass123
(dev DB only — re-arm after a DB reset with:
  UPDATE users SET password_hash='<bcrypt of testpass123>',
         auth_provider='EMAIL' WHERE email='test@example.com';)
"""
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


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    selector = sys.argv[2] if len(sys.argv) > 2 else None
    token = login_token()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, vp in [
            ("mobile", {"width": 390, "height": 1200}),
            ("desktop", {"width": 1280, "height": 1200}),
        ]:
            ctx = browser.new_context(viewport=vp)
            page = ctx.new_page()
            page.goto(f"{BASE}/login")
            page.evaluate(f"localStorage.setItem('predictor_token', '{token}')")
            page.goto(f"{BASE}{path}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1200)  # fonts/flags settle
            out = f"/tmp/shot_{name}.png"
            if selector:
                # Desktop/mobile variants of the same widget coexist in the
                # DOM (CSS hides one) — screenshot the visible match.
                locs = page.locator(selector)
                target = next(
                    (locs.nth(i) for i in range(locs.count()) if locs.nth(i).is_visible()),
                    None,
                )
                if target is None:
                    sys.exit(f"no visible element for selector: {selector}")
                target.scroll_into_view_if_needed()
                target.screenshot(path=out)
            else:
                page.screenshot(path=out, full_page=True)
            print(out)
            ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
