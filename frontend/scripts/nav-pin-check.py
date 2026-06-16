#!/usr/bin/env python3
"""Verify the mobile bottom nav stays pinned to the viewport bottom.

ARCHITECTURE (post nav-stranding deep-dive): the app uses an APP-SHELL layout.
The page shell (.pn-shell) is exactly one viewport tall and overflow:hidden —
it NEVER scrolls. The inner <main class="pn-body"> is the SINGLE scroll
container, and the bottom nav is a STATIC in-flow flex child that sits at the
bottom by layout (not position:sticky/fixed). That removes the nav from the
viewport-anchored composited-layer class that iOS standalone WebKit strands at
a stale offset on app resume — the Heisenbug the earlier fixed→sticky + nudge
+ dvh attempts could not kill.

This script is the LAYOUT regression loop for that model. It runs in
Playwright's WEBKIT build (the iOS Safari engine) with iPhone emulation and,
for every route, asserts the app-shell invariants:

    1. nav.getBoundingClientRect().bottom == window.innerHeight  (±2px)
       at top / mid / bottom scroll, after viewport shrink+restore, and
       through a focus-shrink-blur-restore keyboard cycle.
    2. The DOCUMENT does not scroll — .pn-body is the only scroller.
    3. No position:fixed element is a descendant of .pn-body. A fixed child
       inside a -webkit-overflow-scrolling:touch container can ALSO strand on
       iOS — i.e. this is the way the bug could be silently reintroduced.

What it CANNOT reproduce is the on-device compositor stranding itself: that
needs a real OS suspend/resume of an installed standalone PWA (GPU layer
teardown), which headless WebKit never undergoes. A green run here is
necessary but NOT sufficient — the only valid acceptance gate is the on-device
background+resume loop. See the deep-dive notes / project memory.

Run (dev stack up, dev login armed — see dev-screenshot.py):
    python3 frontend/scripts/nav-pin-check.py            # all routes
    python3 frontend/scripts/nav-pin-check.py /results   # one route
Exits non-zero on any violation, printing route + scenario.
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


def body_metrics(page) -> dict | None:
    """Scroll metrics of the inner .pn-body scroller (None if absent)."""
    return page.evaluate(
        """() => {
            const b = document.querySelector('.pn-shell main.pn-body');
            if (!b) return null;
            return { scrollH: b.scrollHeight, clientH: b.clientHeight };
        }"""
    )


def scroll_body(page, y: float) -> None:
    page.evaluate(
        "(y) => { const b = document.querySelector('.pn-shell main.pn-body'); if (b) b.scrollTop = y; }",
        y,
    )


def document_scrolls(page) -> bool:
    """App-shell invariant: the document itself must NOT scroll."""
    return page.evaluate(
        "() => document.scrollingElement.scrollHeight > window.innerHeight + 2"
    )


def fixed_in_scroller(page) -> int:
    """Count position:fixed elements nested inside .pn-body — these can strand
    inside an iOS momentum scroller and would reintroduce the bug."""
    return page.evaluate(
        """() => {
            const b = document.querySelector('.pn-shell main.pn-body');
            if (!b) return 0;
            return [...b.querySelectorAll('*')]
                .filter(el => getComputedStyle(el).position === 'fixed').length;
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

    # App-shell structural invariants (independent of scroll position).
    if document_scrolls(page):
        failures.append(
            f"{path}: document scrolls — app-shell broken "
            f"(.pn-body must be the only scroller, .pn-shell overflow:hidden)"
        )
    n_fixed = fixed_in_scroller(page)
    if n_fixed:
        failures.append(
            f"{path}: {n_fixed} position:fixed element(s) inside .pn-body — "
            f"can strand on iOS; move them out of the scroller"
        )

    body = body_metrics(page)
    assert_pinned("top")
    if body and body["scrollH"] > body["clientH"] + 10:
        scroll_body(page, body["scrollH"] / 2)
        page.wait_for_timeout(150)
        assert_pinned("mid-scroll")
        scroll_body(page, body["scrollH"])
        page.wait_for_timeout(150)
        assert_pinned("bottom-scroll")
        scroll_body(page, 0)

    # Keyboard-ish viewport shrink + restore: the static nav must stay pinned.
    vp = page.viewport_size
    page.set_viewport_size({"width": vp["width"], "height": vp["height"] - 280})
    page.wait_for_timeout(150)
    assert_pinned("shrunk-viewport")
    page.set_viewport_size(vp)
    page.wait_for_timeout(150)
    assert_pinned("restored-viewport")

    # Full keyboard cycle where the page has an input: focus (iOS would raise
    # the keyboard), shrink, blur (dismiss), restore.
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
    print("\nall routes pinned (layout) — NB: on-device resume test still required")


if __name__ == "__main__":
    main()
