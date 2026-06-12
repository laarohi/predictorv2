#!/usr/bin/env python3
"""Verify the mobile bottom nav stays pinned to the viewport bottom.

The nav is position:sticky on the page shell's .mobile-only wrapper
(commit 3fdf489 — iOS standalone strands position:fixed layers). Sticky
fails SILENTLY if any ancestor becomes a scroll container (an
overflow-x:hidden is enough), if a route scrolls an inner element
instead of the document, or if the shell's height math leaves the nav's
natural position off the visual bottom. Those are layout-engine
behaviours, so they reproduce in Playwright's WEBKIT build (the iOS
Safari engine) with iPhone emulation — this script is the regression
loop for them. (The one thing it can't reproduce is the iOS standalone
compositor losing track of layers on app resume / keyboard dismissal —
see the visualViewport nudge in PnBottomNav.)

For every route it checks, at top / mid / bottom scroll and after a
viewport-height shrink+restore (keyboard-ish resize):

    nav.getBoundingClientRect().bottom == window.innerHeight  (±2px)

Run (dev stack up, dev login armed — see dev-screenshot.py):
    python3 frontend/scripts/nav-pin-check.py            # all routes
    python3 frontend/scripts/nav-pin-check.py /results   # one route
Exits non-zero on any unpinned position, printing route + scenario.
"""

import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
API = "http://localhost:8000"
EMAIL, PASSWORD = "test@example.com", "testpass123"
TOLERANCE = 2  # px — sub-pixel viewport rounding

ROUTES = [
    "/",
    "/predictions",
    "/predictions/overview",
    "/predictions/overview?tab=knockout",
    "/predictions/overview?tab=bonus",
    "/leaderboard",
    "/leaderboard?view=progression",
    "/results",
    "/rules",
    "/profile",
]


def login_token() -> str:
    req = urllib.request.Request(
        f"{API}/api/auth/login",
        data=json.dumps({"email": EMAIL, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req))["access_token"]


def nav_gap(page) -> float | None:
    """How far the visible bottom nav's bottom edge sits from the viewport
    bottom (0 = pinned). None if no nav is rendered (e.g. desktop layout)."""
    return page.evaluate(
        """() => {
            const navs = [...document.querySelectorAll('.pn-mob-tab')];
            const nav = navs.find(n => n.offsetParent !== null);
            if (!nav) return null;
            return window.innerHeight - nav.getBoundingClientRect().bottom;
        }"""
    )


def check_route(page, path: str) -> list[str]:
    failures: list[str] = []
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)

    def assert_pinned(scenario: str):
        gap = nav_gap(page)
        if gap is None:
            failures.append(f"{path} [{scenario}]: nav not rendered")
        elif abs(gap) > TOLERANCE:
            failures.append(f"{path} [{scenario}]: nav off-bottom by {gap:.1f}px")

    doc_h = page.evaluate("document.documentElement.scrollHeight")
    win_h = page.evaluate("window.innerHeight")

    assert_pinned("top")
    if doc_h > win_h + 10:
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight / 2)")
        page.wait_for_timeout(150)
        assert_pinned("mid-scroll")
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(150)
        assert_pinned("bottom-scroll")

    # Keyboard-ish viewport shrink + restore: sticky must re-anchor.
    vp = page.viewport_size
    page.set_viewport_size({"width": vp["width"], "height": vp["height"] - 280})
    page.wait_for_timeout(150)
    assert_pinned("shrunk-viewport")
    page.set_viewport_size(vp)
    page.wait_for_timeout(150)
    assert_pinned("restored-viewport")

    # Full keyboard cycle where the page has an input: focus (iOS would
    # raise the keyboard), shrink, blur (dismiss), restore. Exercises the
    # PnPageShell visualViewport re-anchor nudge end to end.
    has_input = page.evaluate(
        "() => !!document.querySelector('input:not([type=hidden]), textarea')"
    )
    if has_input:
        page.evaluate("document.querySelector('input:not([type=hidden]), textarea').focus()")
        page.set_viewport_size({"width": vp["width"], "height": vp["height"] - 280})
        page.wait_for_timeout(150)
        page.evaluate("document.activeElement && document.activeElement.blur()")
        page.set_viewport_size(vp)
        page.wait_for_timeout(250)
        assert_pinned("keyboard-cycle")

    return failures


def main() -> None:
    routes = sys.argv[1:] or ROUTES
    token = login_token()
    failures: list[str] = []

    with sync_playwright() as p:
        iphone = p.devices["iPhone 13"]
        browser = p.webkit.launch()
        ctx = browser.new_context(**iphone)
        page = ctx.new_page()
        page.goto(f"{BASE}/login")
        page.evaluate(f"localStorage.setItem('predictor_token', '{token}')")

        for path in routes:
            errs = check_route(page, path)
            status = "FAIL" if errs else "ok"
            print(f"{status:>4}  {path}")
            failures.extend(errs)
        browser.close()

    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    print("\nall routes pinned")


if __name__ == "__main__":
    main()
