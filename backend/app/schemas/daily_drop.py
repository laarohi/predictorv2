"""Schemas for the Daily Drop — the once-a-day broadcast banter card.

Each stat is its own optional model: when there isn't enough data yet (no
second snapshot day, no finished matches in the window, no qualifying streak),
the field is ``None`` and the card simply omits that row. That keeps the card
truthful early in the tournament AND helps it fit one screen.

Stored verbatim in ``DailyDrop.payload`` (a JSON column) via
``DropPayload.model_dump(mode="json")``; the same shape is returned by the API.
"""

from datetime import date, datetime

from pydantic import BaseModel


# Broadcast stats carry the FULL set of tied players (``names``), deterministically
# ordered (alphabetical). The frontend formats the list with overflow
# ("A", "A & B", "A, B & C", "A, B +N"). Per-person detail fields that ties can't
# share (e.g. a specific from→to rank) are deliberately omitted.


class LeaderStat(BaseModel):
    """👑 Who's top (all co-leaders), and the gap to the chasing pack."""

    names: list[str]
    points: int
    lead: int  # gap to the next distinct position (0 if everyone's level)
    # Consecutive days this exact leader (set) has been top, per snapshots
    # (1 = just took the lead). Lets the roast avoid re-roasting a static leader.
    days_held: int = 1


class MoveStat(BaseModel):
    """📈 Mover / 💀 Faceplant — overnight rank change. ``delta`` is +ve for a
    climb, −ve for a drop; every listed player shares it."""

    names: list[str]
    delta: int


class PointsHaulStat(BaseModel):
    """⚡ Most points banked between the last two snapshots."""

    names: list[str]
    points_gained: int


class SpoonStat(BaseModel):
    """🥄 Dead last among real players (position ties share points → behind)."""

    names: list[str]
    position: int
    behind_leader: int
    # Consecutive days this exact bottom (set) has propped up the table, per
    # snapshots (1 = first day down there). Roast uses it to avoid piling on.
    days_held: int = 1


class CalledItStat(BaseModel):
    """🎯 The rarest correct EXACT score in the window. ``names`` is a SINGLE
    winner (least-featured-of-the-tied); ``count`` is how many nailed it (1 = solo)."""

    names: list[str]  # single element (one player per picks award)
    count: int  # how many players nailed this exact score (1 → "SOLO")
    home_team: str
    away_team: str
    home_score: int
    away_score: int


class ContrarianStat(BaseModel):
    """🧠 The Hipster — the player whose picks were the LEAST popular across the
    whole day: lowest AVERAGE share of the rest of the pool that made the same
    outcome call, over every match settled that day. ``names`` is a single winner."""

    names: list[str]  # single element (one player per picks award)
    avg_pct: int  # avg % of OTHER players who agreed with their picks (lower = more contrarian)


class BlunderStat(BaseModel):
    """🤡 What were you thinking — the most wrongly-confident pick. ``names`` is
    everyone who made the IDENTICAL pick on the same match (shared scoreline)."""

    names: list[str]
    home_team: str
    away_team: str
    predicted: str  # "3-0"
    actual: str  # "0-3"
    swing: int  # |predicted_gd - actual_gd|


class StreakStat(BaseModel):
    """🔥 Hottest / 🧊 Coldest current run on the board (all tied at the top)."""

    names: list[str]
    length: int


class PointsCategory(BaseModel):
    """One non-zero slice of the viewer's points (exact / outcome / rarity /
    bonus questions / a bracket round). Zero categories are dropped first."""

    label: str
    points: int


class PersonalStats(BaseModel):
    """The VIEWER's own day — computed per-request (not part of the broadcast
    payload). Powers the personalised "Your Day" story page."""

    user_name: str
    position: int
    movement: int  # day-over-day rank change (+ = climbed)
    points: int
    points_gained: int | None  # vs yesterday's snapshot (None if no baseline)
    hot_streak: int
    cold_streak: int
    points_breakdown: list[PointsCategory] = []  # non-zero categories only


class DropPayload(BaseModel):
    """The full computed card. Every stat is optional → omitted rows hide."""

    # Standings
    leader: LeaderStat | None = None
    mover: MoveStat | None = None
    faceplant: MoveStat | None = None
    points_haul: PointsHaulStat | None = None
    wooden_spoon: SpoonStat | None = None
    # Picks
    called_it: CalledItStat | None = None
    contrarian: ContrarianStat | None = None
    blunder: BlunderStat | None = None
    # Form
    hottest_streak: StreakStat | None = None
    coldest_streak: StreakStat | None = None
    # Context
    match_count: int = 0  # finished matches the pick stats drew from
    player_count: int = 0  # real (non-ghost) players on the board


class DailyDropResponse(BaseModel):
    """What the modal fetches: the day's stats + (maybe) the roast."""

    drop_date: date
    payload: DropPayload
    roast: str | None = None
    # True when ``roast`` is a synthesized stand-in (no real roast stored yet) —
    # lets the modal flag it as a sample rather than the genuine article.
    roast_is_placeholder: bool = False
    roast_generated_at: datetime | None = None
    created_at: datetime
    # The requesting viewer's own stats (per-request; null for anonymous/ghost
    # or a viewer with no board entry). Powers the "Your Day" page.
    personal: PersonalStats | None = None
