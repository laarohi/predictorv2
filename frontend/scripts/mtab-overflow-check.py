#!/usr/bin/env python3
"""Measure .mtab horizontal overflow at mobile width, with a LIVE row present.

Reproduces the dashboard "Upcoming matches" bug where an in-play match adds
the Status column (hasStatusCol -> 5 cols) and pushes the POINTS column off
the right edge. Injects the exact DwMatchTable DOM into a real, fully-styled
dashboard page (real fonts + .pn scope + panini-dashboard-v4.css) so the
measurement reflects production CSS, then reports per-cell overflow.

Usage: python3 frontend/scripts/mtab-overflow-check.py
Writes /tmp/mtab_375.png and /tmp/mtab_390.png and prints overflow numbers.
"""
import json
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
API = "http://localhost:8000"
EMAIL, PASSWORD = "test@example.com", "testpass123"

# A faux flag box — the real PnFlag renders an SVG, but the mobile rule pins
# .pn .mtab .pn-flag to 18x12 regardless, so an inline-block stand-in gives
# the same grid min-content contribution.
FLAG = '<span class="pn-flag" style="display:inline-block;background:#9aa;"></span>'

# Mirror of DwMatchTable.svelte markup (lines 92-171) for a table that has a
# live row (so hasStatusCol is true -> 5 columns). One live + three upcoming,
# matching the user's screenshot.
FIXTURE = f"""
<div class="pn" id="mtab-probe">
  <div class="pn-dash-v4" style="max-width:none;margin:0;">
    <div class="mtab">
      <div class="mtab-head">
        <span class="c-status"></span>
        <span class="c-grp">Rnd</span>
        <span class="c-match">Match</span>
        <span class="c-pick">Pick</span>
        <span class="c-pts">Points</span>
      </div>
      <div class="mtab-row live">
        <span class="status live">90<span class="tick">′</span></span>
        <span class="grp ko">ROU</span>
        <div class="c-match">
          <span class="team home">{FLAG}RSA</span>
          <span class="sc live"><span>0</span><span class="dash">–</span><span>1</span></span>
          <span class="team away">CAN{FLAG}</span>
        </div>
        <div class="c-pick"><span class="pick">0<span class="dash">–</span>2</span></div>
        <div class="c-pts"><span class="pts">+5</span></div>
      </div>
      <div class="mtab-row">
        <span class="status"></span>
        <span class="grp ko">ROU</span>
        <div class="c-match">
          <span class="team home">{FLAG}BRA</span>
          <span class="sc vs ko">MON 19:00</span>
          <span class="team away">JPN{FLAG}</span>
        </div>
        <div class="c-pick"><span class="pick">1<span class="dash">–</span>1</span></div>
        <div class="c-pts"><a class="cta secondary">Edit</a></div>
      </div>
      <div class="mtab-row">
        <span class="status"></span>
        <span class="grp ko">ROU</span>
        <div class="c-match">
          <span class="team home">{FLAG}GER</span>
          <span class="sc vs ko">MON 22:30</span>
          <span class="team away">PAR{FLAG}</span>
        </div>
        <div class="c-pick"><span class="pick">2<span class="dash">–</span>0</span></div>
        <div class="c-pts"><a class="cta secondary">Edit</a></div>
      </div>
    </div>
  </div>
</div>
"""

MEASURE = """
() => {
  const mtab = document.querySelector('#mtab-probe .mtab');
  const mr = mtab.getBoundingClientRect();
  const liveRow = document.querySelector('#mtab-probe .mtab-row.live');
  const pts = liveRow.querySelector('.c-pts');
  const pr = pts.getBoundingClientRect();
  const match = liveRow.querySelector('.c-match');
  return {
    mtab_client: Math.round(mtab.clientWidth),
    mtab_scroll: Math.round(mtab.scrollWidth),
    // table overflow past its container (0 once Match is the shrink point)
    overflow_px: Math.round(mtab.scrollWidth - mtab.clientWidth),
    // how far the POINTS cell sticks out past the table edge (the bug)
    pts_clipped_px: Math.round(pr.right - mr.right),
    // once Match can shrink, THIS is the signal: does match content (flags +
    // codes + score) overflow its squeezed cell? >0 means flags clip.
    match_content_overflow_px: Math.round(match.scrollWidth - match.clientWidth),
  };
}
"""


def login_token() -> str:
    req = urllib.request.Request(
        f"{API}/api/auth/login",
        data=json.dumps({"email": EMAIL, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req))["access_token"]


def main() -> None:
    token = login_token()
    # (label, viewport_width, slot_width) — slot_width caps .pn-dash-v4 to mimic
    # the desktop 1/3 dashboard column; None = full width (phones).
    scenarios = [
        ("375", 375, None),
        ("390", 390, None),
        ("desktop-slot", 1280, 460),
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, width, slot in scenarios:
            ctx = browser.new_context(viewport={"width": width, "height": 1400})
            page = ctx.new_page()
            page.goto(f"{BASE}/login")
            page.evaluate(f"localStorage.setItem('predictor_token', '{token}')")
            page.goto(f"{BASE}/")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1000)
            html = FIXTURE
            if slot:
                html = html.replace("max-width:none;", f"max-width:{slot}px;")
            page.evaluate(
                "(html) => { const d=document.createElement('div'); d.innerHTML=html;"
                " document.body.prepend(d.firstElementChild); window.scrollTo(0,0); }",
                html,
            )
            page.wait_for_timeout(400)
            res = page.evaluate(MEASURE)
            print(f"--- {label} (viewport {width}px, slot {slot}) ---")
            for k, v in res.items():
                print(f"  {k}: {v}")
            page.locator("#mtab-probe .mtab").screenshot(path=f"/tmp/mtab_{label}.png")
            print(f"  screenshot: /tmp/mtab_{label}.png")
            ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
