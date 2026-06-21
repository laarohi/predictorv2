"""Phase C — the Daily Drop's savage roast, written by Claude on the user's
Claude Code subscription (via the ``roaster`` sidecar).

The backend owns all the logic here: it loads the per-person dossiers from
``config/roasts.yml``, turns the day's computed stats into a readable brief,
and POSTs the assembled prompt to the sidecar. The sidecar runs ``claude -p``
headless and returns plain text. Any failure (no sidecar, timeout, blank reply)
returns ``None`` so the caller falls back to the deterministic placeholder — the
Drop is never blocked on the LLM.
"""

import asyncio
import logging
from pathlib import Path

import httpx
import yaml

from app.config import get_settings
from app.schemas.daily_drop import DropPayload

logger = logging.getLogger(__name__)

# Every broadcast stat in the payload, in card order — single source of truth for
# "who features today" (dossier selection) and the brief.
_STAT_FIELDS = (
    "leader",
    "mover",
    "faceplant",
    "points_haul",
    "wooden_spoon",
    "clueless",
    "called_it",
    "contrarian",
    "blunder",
    "hottest_streak",
    "coldest_streak",
)


def _roasts_path() -> Path:
    """``roasts.yml`` lives beside the tournament config (same mounted dir)."""
    return Path(get_settings().tournament_config_path).resolve().parent / "roasts.yml"


def _load_dossiers() -> tuple[str, dict[str, str]]:
    """``(tone, {display_name: one-line note})``. Only non-blank notes are kept.
    A missing or malformed file degrades to ``("", {})``."""
    try:
        raw = yaml.safe_load(_roasts_path().read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("roasts.yml unreadable (%s) — roasting without dossiers", exc)
        return "", {}
    tone = str(raw.get("tone") or "").strip()
    players = raw.get("players") or {}
    notes = {
        str(name): str(desc).strip()
        for name, desc in players.items()
        if isinstance(desc, str) and desc.strip()
    }
    return tone, notes


def _names(stat) -> list[str]:
    return list(getattr(stat, "names", []) or []) if stat else []


def _join(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _brief(p: DropPayload) -> list[str]:
    """Each present stat as one plain-English line for the prompt."""
    lines: list[str] = []
    if p.leader:
        gap = f", {p.leader.lead} clear" if p.leader.lead > 0 else " (level at the top)"
        tenure = (
            f" — and has led for {p.leader.days_held} days running"
            if p.leader.days_held >= 2 else ""
        )
        lines.append(
            f"- Top of the table: {_join(p.leader.names)} on {p.leader.points} pts{gap}{tenure}."
        )
    if p.mover:
        lines.append(
            f"- Biggest climber overnight: {_join(p.mover.names)}, up {p.mover.delta} place(s)."
        )
    if p.faceplant:
        lines.append(
            f"- Biggest faller overnight: {_join(p.faceplant.names)}, "
            f"down {abs(p.faceplant.delta)} place(s)."
        )
    if p.points_haul:
        lines.append(
            f"- Most points banked: {_join(p.points_haul.names)} (+{p.points_haul.points_gained})."
        )
    if p.wooden_spoon:
        tenure = (
            f", rooted to the bottom for {p.wooden_spoon.days_held} days now"
            if p.wooden_spoon.days_held >= 2 else ""
        )
        lines.append(
            f"- Dead last: {_join(p.wooden_spoon.names)}, "
            f"{p.wooden_spoon.behind_leader} pts off the top{tenure}."
        )
    if p.clueless:
        c = p.clueless
        extra = c.tied_count - len(c.names)
        others = (
            f" — along with {extra} other{'s' if extra != 1 else ''} on the same"
            if extra > 0 else ""
        )
        verb = (
            "didn't trouble the scorers at all today"
            if c.is_floor
            else f"scraped just {c.points} pt{'s' if c.points != 1 else ''} today"
        )
        lines.append(f"- Clueless (worst on the day): {_join(c.names)} {verb}{others}.")
    if p.called_it:
        c = p.called_it
        lines.append(
            f"- Rarest exact score nailed: {_join(c.names)} called "
            f"{c.home_team} {c.home_score}-{c.away_score} {c.away_team}."
        )
    if p.contrarian:
        c = p.contrarian
        lines.append(
            f"- The Hipster (least popular picks all day): {_join(c.names)} — on "
            f"average only ~{c.avg_pct}% of the pool made the same calls as them."
        )
    if p.blunder:
        b = p.blunder
        lines.append(
            f"- Worst pick of the day: {_join(b.names)} said {b.predicted} for "
            f"{b.home_team} v {b.away_team}; it finished {b.actual}."
        )
    if p.hottest_streak:
        lines.append(
            f"- Hottest streak: {_join(p.hottest_streak.names)}, "
            f"{p.hottest_streak.length} correct in a row."
        )
    if p.coldest_streak:
        lines.append(
            f"- Coldest streak: {_join(p.coldest_streak.names)}, "
            f"{p.coldest_streak.length} wrong in a row."
        )
    return lines


def _length_guidance(p: DropPayload) -> str:
    """Scale the roast to how much actually happened — a big day earns a fuller
    roast, a quiet day a short zinger. Varying length paces the material across a
    long tournament and keeps the cadence from feeling formulaic."""
    present = sum(1 for f in _STAT_FIELDS if getattr(p, f) is not None)
    if p.match_count >= 3 or present >= 7:
        return "7 to 9 sentences — it was a big day, so make it a proper roast"
    if present >= 4:
        return "4 to 5 punchy sentences"
    return "just 2 to 3 sharp sentences — a quiet day, so keep it short and lethal"


def build_prompt(p: DropPayload, past_roasts: list[str] | None = None) -> str:
    """Assemble the full roast prompt: the day's stats, the dossiers of the people
    featured today, and the running log of every previous roast (so jokes never
    repeat). ``past_roasts`` is the whole-tournament history, oldest first."""
    tone, notes = _load_dossiers()
    brief = _brief(p)

    featured = sorted({n for f in _STAT_FIELDS for n in _names(getattr(p, f))})
    dossiers = [f"- {n}: {notes[n]}" for n in featured if n in notes]

    parts = [
        "You are the resident piss-taker for a World Cup 2026 score-prediction "
        "league played by a group of close mates. Write today's roast for the "
        "group chat.",
        "",
        "TONE:",
        tone
        or "Savage but good-natured football banter between friends who can take a hit.",
        "",
        "TODAY ON THE BOARD:",
        *(brief or ["- A quiet day — nobody did anything spectacular or catastrophic."]),
    ]
    if dossiers:
        parts += [
            "",
            "WHAT YOU KNOW ABOUT THE PEOPLE INVOLVED (optional colour, not a checklist):",
            *dossiers,
        ]
    if past_roasts:
        parts += [
            "",
            "RUNNING LOG — every roast so far this tournament (oldest first). This is "
            "your no-repeat list: do NOT reuse these jokes, angles, metaphors or "
            "phrasings. Revisiting a person or a theme is fine ONLY from a genuinely "
            "different angle (e.g. another lawyer joke about Ed is allowed, but it "
            "must not echo one already used):",
            *(f"[Day {i}] {r}" for i, r in enumerate(past_roasts, 1)),
        ]
    # When the same player has sat top/bottom for several days, re-roasting them
    # for it is stale — tell the model to leave them be unless it has a NEW hook.
    stale = []
    if p.leader and p.leader.days_held >= 3:
        stale.append(f"{_join(p.leader.names)} (top {p.leader.days_held} days)")
    if p.wooden_spoon and p.wooden_spoon.days_held >= 3:
        stale.append(f"{_join(p.wooden_spoon.names)} (bottom {p.wooden_spoon.days_held} days)")

    parts += [
        "",
        f"Context: {p.match_count} match(es) settled, {p.player_count} players in the pool.",
        "",
        "INSTRUCTIONS:",
        f"- Length: {_length_guidance(p)}. One paragraph, plain text.",
        "- HARD LIMIT: never exceed 9 sentences or ~140 words — the roast must fit on "
        "a phone screen with no scrolling. If in doubt, cut it shorter; a tight roast "
        "that lands beats a long one that gets cut off.",
        "- Name and roast 2 to 4 of the people above, using their EXACT display name.",
    ]
    if stale:
        parts.append(
            "- OLD NEWS — " + "; ".join(stale) + ". Don't roast them just for being "
            "top/bottom again; the group's heard it. Only feature them with a "
            "genuinely fresh angle (a specific pick, a dossier detail), otherwise "
            "lean on the day's movers, blunders and the chasing pack instead."
        )
    parts += [
        "- Mix it up day to day: you do NOT have to use the dossier notes. Some roasts "
        "should lean on personal details, others should roast purely on their "
        "predictions and table position, and you're encouraged to invent your own "
        "sharp observational digs. Keep people guessing.",
        "- Above all, go after the actual predictions and standings of the day.",
        "- Do not repeat anything from the running log above (if present).",
        "- Plain text only: no markdown, no lists, no emojis, no preamble, no "
        "sign-off. Output ONLY the roast itself.",
    ]
    return "\n".join(parts)


async def generate_roast(p: DropPayload, past_roasts: list[str] | None = None) -> str | None:
    """Ask the roaster sidecar for today's roast, given the running log of past
    roasts (for no-repeat). ``None`` on any failure."""
    base = (get_settings().roaster_url or "").strip().rstrip("/")
    if not base:
        return None
    prompt = build_prompt(p, past_roasts)
    # Once-a-day job → cheap to retry. The Claude CLI throws the occasional
    # transient 500; a second attempt almost always lands it. All attempts
    # exhausted → None (caller keeps the deterministic placeholder).
    attempts = 3
    # 190s: comfortably above the roaster's own ROAST_TIMEOUT_MS (180s) so the
    # sidecar's clean "claude timed out" reply wins over an httpx abort. A real
    # roast generates in ~75-80s; the headroom absorbs a slow API morning that
    # used to tip past the old 95s cap and fall back to the placeholder.
    async with httpx.AsyncClient(timeout=httpx.Timeout(190.0)) as client:
        for attempt in range(1, attempts + 1):
            try:
                resp = await client.post(f"{base}/roast", json={"prompt": prompt})
                resp.raise_for_status()
                roast = str((resp.json() or {}).get("roast") or "").strip()
                if roast:
                    return roast
                logger.warning("roast came back empty (attempt %d/%d)", attempt, attempts)
            except Exception as exc:  # sidecar down, timeout, http error, bad json
                logger.warning("roast attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(2 * attempt)  # 2s, then 4s backoff
    logger.warning("roast generation gave up after %d attempts — using placeholder", attempts)
    return None
