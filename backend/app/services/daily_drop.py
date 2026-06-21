"""Compute (and persist) the Daily Drop — the once-a-day broadcast banter card.

The card is BROADCAST (identical for everyone); the only per-user touch is the
morning push text, handled elsewhere. Everything here is derived from data that
already exists:

- **leader / wooden_spoon / hottest_streak / coldest_streak** — from the live
  ``calculate_leaderboard`` (which already carries hot/cold streaks).
- **mover / faceplant** — from the live board's day-over-day rank movement
  (``entry.movement``), i.e. the SAME number the leaderboard chip shows: live
  position now vs the latest prior-day snapshot. (Previously a frozen
  snapshot-to-snapshot diff, which could disagree in sign with the chip — the
  bug this fixes.)
- **points_haul / clueless** — best / worst points scored in the day's 24h
  window, summed per player from the same match scoring as "Your Day", so the
  three can never disagree.
- **called_it / contrarian / blunder** — from predictions joined to scores for
  matches that finished in the recent window.

Every delta and window here means ONE thing: the rolling 24h up to the drop's
build time (``WINDOW_HOURS``). The drop is a static snapshot of that moment, so
it agrees with the live leaderboard AT drop time and may legitimately drift as
more of today's matches finish.

Every stat is independently nullable: missing data → that row is omitted, which
keeps the card honest early on and helps it fit one screen.

The roast is NOT generated here — it's written separately by Claude (on the
user's Claude Code subscription) and stored on the same row; ``roast`` stays
NULL until then.
"""

import asyncio
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import utc_now
from app.models.daily_drop import DailyDrop
from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import MatchPrediction
from app.models.score import Score
from app.models.user import User
from app.services.roast import generate_roast
from app.schemas.daily_drop import (
    BlunderStat,
    CalledItStat,
    CluelessStat,
    ContrarianStat,
    DropPayload,
    LeaderStat,
    MatchResult,
    MoveStat,
    PersonalStats,
    PointsHaulStat,
    SpoonStat,
    StreakStat,
)
from app.services.leaderboard import calculate_leaderboard

# THE canonical drop window: every match-derived stat (picks awards, points_haul,
# clueless, "Your Day") counts matches that finished in the 24h before the drop's
# build time. One window, one meaning of "today", anchored to the drop — never the
# viewer's clock. A 24h window back from an ~08:30-Malta build spans exactly the
# prior day's slate (which finishes well before midnight UTC) and nothing from the
# current day, so "the last 24h" and "yesterday's games" are the same set.
WINDOW_HOURS = 24

# A streak only earns a card slot once it's actually a streak (matches the
# leaderboard chip's STREAK_MIN).
STREAK_MIN = 2

# Clueless lists every tied player up to this many; beyond it (a mass zero-point
# day) it collapses to one rotating representative + a "+N others" count, so the
# card never prints fifteen names.
CLUELESS_NAME_CAP = 3


def _pick_one(candidates: list[str], feature_count: dict[str, int]) -> str:
    """Each picks-page award shows ONE player. When several tie, give it to the
    one featured fewest times so far (alphabetical tiebreak) so the awards spread
    across the group instead of one person sweeping the page. Records the pick."""
    winner = min(sorted(candidates), key=lambda n: feature_count.get(n, 0))
    feature_count[winner] = feature_count.get(winner, 0) + 1
    return winner


def _clueless_stat(
    daily_points: dict[uuid.UUID, int],
    names: dict[uuid.UUID, str],
    *,
    reference: datetime,
    feature_count: dict[str, int],
) -> CluelessStat | None:
    """The day's worst performer(s) — fewest points won in the drop window, over
    players who predicted at least one window match (``daily_points`` keys).

    Needs at least two players (someone has to be the *worst*), and is suppressed
    when everyone is level on a non-zero score (no genuine dunce). A small tied
    set lists everyone; a big one (the mass zero-point floor) collapses to a
    single representative — rotated by the drop's date so it isn't the same name
    every blank day — plus a ``tied_count`` the card shows as "+N"."""
    if len(daily_points) < 2:
        return None
    min_pts = min(daily_points.values())
    max_pts = max(daily_points.values())
    if min_pts == max_pts and min_pts != 0:
        return None  # everyone level on a real score — nobody stands out as clueless

    tied = sorted(names.get(u, "?") for u, v in daily_points.items() if v == min_pts)
    tied_count = len(tied)
    if tied_count <= CLUELESS_NAME_CAP:
        shown = tied
        for n in shown:
            feature_count[n] = feature_count.get(n, 0) + 1
    else:
        # Rotate the named scapegoat across days so a mass-zero day doesn't keep
        # singling out the alphabetically-first player. Deterministic per drop.
        winner = tied[reference.toordinal() % tied_count]
        feature_count[winner] = feature_count.get(winner, 0) + 1
        shown = [winner]
    return CluelessStat(
        names=shown, points=min_pts, tied_count=tied_count, is_floor=(min_pts == 0)
    )


async def _daily_points(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    ghost_ids: set[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Per real player, the points they scored on matches that FINISHED in the
    drop window (kickoff in ``[since, until]``). The multi-user generalisation of
    the "Your Day" recap, computed with the SAME match scoring — so "Big Earner",
    "Clueless" and "Your Day" can never disagree.

    Only players who predicted at least one window match appear (a key with value
    0 means "played and scored nothing"; absent means "didn't play" — not the same
    as clueless). Ghosts (crowd / market) are excluded from the result, but the
    pool-agreement counts that feed the rarity bonus are taken over everyone, exactly
    as the live scoring does.
    """
    # Local import: scoring pulls in the config + bonus layers; importing at module
    # load would widen this service's import graph.
    from app.services.scoring import calculate_match_points, get_outcome_counts

    rows = (
        await session.execute(
            select(MatchPrediction, Score, Fixture)
            .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
            .join(Score, Score.fixture_id == Fixture.id)
            .where(
                Fixture.status == MatchStatus.FINISHED,
                Fixture.kickoff >= since,
                Fixture.kickoff <= until,
            )
        )
    ).all()

    counts_cache: dict[uuid.UUID, dict[str, int]] = {}
    totals: dict[uuid.UUID, int] = {}
    for prediction, score, fixture in rows:
        if prediction.user_id in ghost_ids:
            continue
        counts = counts_cache.get(fixture.id)
        if counts is None:
            counts = await get_outcome_counts(session, fixture.id)
            counts_cache[fixture.id] = counts
        points, _, _ = calculate_match_points(
            prediction, score,
            total_predictors=sum(counts.values()),
            correct_predictors=counts.get(score.outcome, 0),
        )
        totals[prediction.user_id] = totals.get(prediction.user_id, 0) + points
    return totals


async def _pick_stats(
    session: AsyncSession,
    *,
    since: datetime,
    until: datetime,
    feature_count: dict[str, int],
) -> tuple[CalledItStat | None, ContrarianStat | None, BlunderStat | None, int]:
    """called_it / hipster / blunder over real players' picks on matches that
    finished with kickoff in ``[since, until]`` (the canonical drop window). ONE
    winner per award (least-featured tiebreak via ``feature_count``). Returns the
    stats + the match count."""
    result = await session.execute(
        select(Fixture, Score, MatchPrediction, User)
        .join(Score, Score.fixture_id == Fixture.id)
        .join(MatchPrediction, MatchPrediction.fixture_id == Fixture.id)
        .join(User, User.id == MatchPrediction.user_id)
        .where(Fixture.status == MatchStatus.FINISHED)
        .where(Fixture.kickoff >= since)
        .where(Fixture.kickoff <= until)
        .where(User.is_ghost == False)  # noqa: E712 — real players only
    )
    rows = list(result.all())
    if not rows:
        return None, None, None, 0

    # Group predictions by fixture; stash one Fixture/Score per id.
    by_fixture: dict[uuid.UUID, list[tuple[MatchPrediction, User]]] = defaultdict(list)
    fixtures: dict[uuid.UUID, Fixture] = {}
    scores: dict[uuid.UUID, Score] = {}
    for fixture, score, pred, user in rows:
        by_fixture[fixture.id].append((pred, user))
        fixtures[fixture.id] = fixture
        scores[fixture.id] = score

    #   called_it : the exact hit on the fixture FEWEST players nailed exactly.
    #   hipster   : the player whose picks were LEAST popular across the day —
    #               lowest avg share of OTHER players who made the same outcome
    #               call, over every settled match.
    #   blunder   : the most wrongly-confident pick (biggest GD swing against);
    #               the tied set = everyone who made that IDENTICAL pick.
    exact_users: dict[uuid.UUID, list[User]] = {}
    called_fid: uuid.UUID | None = None
    called_rarity: int | None = None
    blunder_fid: uuid.UUID | None = None
    blunder_pred: tuple[int, int] | None = None
    blunder_swing = -1

    # Hipster accumulation: average outcome-agreement (excluding self) per user.
    pop_sum: dict[uuid.UUID, float] = defaultdict(float)
    pop_cnt: dict[uuid.UUID, int] = defaultdict(int)
    user_by_id: dict[uuid.UUID, User] = {}

    for fid, preds in by_fixture.items():
        sc = scores[fid]
        exact_users[fid] = [
            u for p, u in preds
            if p.home_score == sc.final_home_score and p.away_score == sc.final_away_score
        ]
        if exact_users[fid] and (called_rarity is None or len(exact_users[fid]) < called_rarity):
            called_rarity = len(exact_users[fid])
            called_fid = fid

        # Popularity of each player's OUTCOME pick on this match (share of the
        # rest of the pool that agreed) → averaged per player for the Hipster.
        total = len(preds)
        outcome_counts: dict[str, int] = defaultdict(int)
        for p, u in preds:
            outcome_counts[p.predicted_outcome] += 1
            user_by_id[u.id] = u
        if total > 1:
            for p, u in preds:
                pop_sum[u.id] += (outcome_counts[p.predicted_outcome] - 1) / (total - 1)
                pop_cnt[u.id] += 1

        actual_gd = sc.final_home_score - sc.final_away_score
        for p, u in preds:
            if p.predicted_outcome == sc.outcome:
                continue  # only WRONG-outcome picks can be blunders
            swing = abs((p.home_score - p.away_score) - actual_gd)
            if swing > blunder_swing:
                blunder_swing = swing
                blunder_fid = fid
                blunder_pred = (p.home_score, p.away_score)

    # One winner per award, in page order (blunder hero, then honours), each
    # spread across the group via least-featured tiebreak.
    blunder: BlunderStat | None = None
    if blunder_fid is not None and blunder_pred is not None:
        fx, sc = fixtures[blunder_fid], scores[blunder_fid]
        ph, pa = blunder_pred
        cands = sorted(
            u.name for p, u in by_fixture[blunder_fid]
            if p.home_score == ph and p.away_score == pa
        )
        blunder = BlunderStat(
            names=[_pick_one(cands, feature_count)],
            home_team=fx.home_team, away_team=fx.away_team,
            predicted=f"{ph}-{pa}",
            actual=f"{sc.final_home_score}-{sc.final_away_score}",
            swing=blunder_swing,
        )

    called_it: CalledItStat | None = None
    if called_fid is not None:
        fx, sc = fixtures[called_fid], scores[called_fid]
        cands = sorted(u.name for u in exact_users[called_fid])
        called_it = CalledItStat(
            names=[_pick_one(cands, feature_count)],
            count=len(exact_users[called_fid]),
            home_team=fx.home_team, away_team=fx.away_team,
            home_score=sc.final_home_score, away_score=sc.final_away_score,
        )

    contrarian: ContrarianStat | None = None
    avgs = {uid: pop_sum[uid] / pop_cnt[uid] for uid in pop_cnt if pop_cnt[uid] > 0}
    if avgs:
        min_avg = min(avgs.values())
        cands = sorted(user_by_id[uid].name for uid, a in avgs.items() if a == min_avg)
        contrarian = ContrarianStat(
            names=[_pick_one(cands, feature_count)],
            avg_pct=round(min_avg * 100),
        )

    return called_it, contrarian, blunder, len(by_fixture)


async def _position_tenure(
    session: AsyncSession, leader_ids: set[uuid.UUID], spoon_ids: set[uuid.UUID]
) -> tuple[int, int]:
    """How many consecutive recent snapshot days the current leader set / spoon
    set has held top / bottom of the table. 1 = only today (or no matching
    history). Lets the roast avoid re-roasting a long-standing first/last."""
    rows = (
        await session.execute(
            select(
                LeaderboardSnapshot.captured_date,
                LeaderboardSnapshot.user_id,
                LeaderboardSnapshot.position,
            )
        )
    ).all()
    by_day: dict[date, dict[uuid.UUID, int]] = defaultdict(dict)
    for d, uid, pos in rows:
        by_day[d][uid] = pos
    days = sorted(by_day.keys(), reverse=True)

    def _streak(target_ids: set[uuid.UUID], edge) -> int:
        # Walk newest→oldest; count days whose top (edge=min) / bottom (edge=max)
        # holders are EXACTLY today's set. Stop at the first day that differs.
        if not target_ids:
            return 1
        count = 0
        for d in days:
            positions = by_day[d]
            if not positions:
                break
            edge_pos = edge(positions.values())
            holders = {u for u, p in positions.items() if p == edge_pos}
            if holders == target_ids:
                count += 1
            else:
                break
        return max(1, count)

    return _streak(leader_ids, min), _streak(spoon_ids, max)


async def compute_drop_payload(
    session: AsyncSession, *, reference: datetime | None = None
) -> DropPayload:
    """Compute the full broadcast card from the live standings and the matches
    that finished in the canonical 24h window. Pure read — persists nothing."""
    reference = reference or utc_now()
    since = reference - timedelta(hours=WINDOW_HOURS)  # the one true window: [since, reference]

    # User name + ghost lookups (one pass).
    users = (await session.execute(select(User))).scalars().all()
    names = {u.id: u.name for u in users}
    ghost_ids = {u.id for u in users if u.is_ghost}

    # --- Standings (live board) ------------------------------------------
    board = await calculate_leaderboard(session)
    ranked = [e for e in board.entries if not e.is_ghost]

    leader = None
    wooden_spoon = None
    if ranked:
        top_pos = min(e.position for e in ranked)
        leaders = [e for e in ranked if e.position == top_pos]
        runner_up_pts = next(
            (e.total_points for e in sorted(ranked, key=lambda e: e.position)
             if e.position > top_pos),
            leaders[0].total_points,
        )
        leader = LeaderStat(
            names=sorted(e.user_name for e in leaders),
            points=leaders[0].total_points,
            lead=leaders[0].total_points - runner_up_pts,
        )
        last_pos = max(e.position for e in ranked)
        # Only a wooden spoon if there's more than one distinct position.
        spooners: list = []
        if last_pos != top_pos:
            spooners = [e for e in ranked if e.position == last_pos]
            wooden_spoon = SpoonStat(
                names=sorted(e.user_name for e in spooners),
                position=last_pos,
                behind_leader=leaders[0].total_points - spooners[0].total_points,
            )

        # How long the current top/bottom have been parked there — the roast
        # uses this to stop piling on a static leader/last every single day.
        leader_days, spoon_days = await _position_tenure(
            session,
            {e.user_id for e in leaders},
            {e.user_id for e in spooners},
        )
        leader.days_held = leader_days
        if wooden_spoon:
            wooden_spoon.days_held = spoon_days

    # Peak streak lengths (board entries); the single winner is chosen BELOW,
    # after the picks awards, so the streaks share the least-featured spread.
    max_hot = max((e.hot_streak for e in ranked), default=0)
    max_cold = max((e.cold_streak for e in ranked), default=0)

    # --- Movement (live board, day-over-day) -----------------------------
    # mover/faceplant read the SAME ``entry.movement`` the leaderboard chip shows
    # (live position now vs the latest prior-day snapshot), so the drop and the
    # table agree at drop time. No movement yet (no prior snapshot) → all 0 → both
    # None, just as before.
    mover = faceplant = None
    if ranked:
        max_move = max(e.movement for e in ranked)
        min_move = min(e.movement for e in ranked)
        if max_move > 0:
            mover = MoveStat(
                names=sorted(e.user_name for e in ranked if e.movement == max_move),
                delta=max_move,
            )
        if min_move < 0:
            faceplant = MoveStat(
                names=sorted(e.user_name for e in ranked if e.movement == min_move),
                delta=min_move,
            )

    # --- Daily points (drives points_haul + clueless; mirrors "Your Day") -
    daily_points = await _daily_points(
        session, since=since, until=reference, ghost_ids=ghost_ids
    )
    points_haul = None
    if daily_points:
        max_gain = max(daily_points.values())
        if max_gain > 0:
            points_haul = PointsHaulStat(
                names=sorted(names.get(u, "?") for u, v in daily_points.items() if v == max_gain),
                points_gained=max_gain,
            )

    # --- Picks (recent finished matches) — ONE winner per award, spread by
    # least-featured across blunder → called_it → hipster → hottest → coldest.
    feature_count: dict[str, int] = {}
    called_it, contrarian, blunder, match_count = await _pick_stats(
        session, since=since, until=reference, feature_count=feature_count
    )
    hottest_streak = (
        StreakStat(
            names=[_pick_one(sorted(e.user_name for e in ranked if e.hot_streak == max_hot), feature_count)],
            length=max_hot,
        )
        if max_hot >= STREAK_MIN
        else None
    )
    coldest_streak = (
        StreakStat(
            names=[_pick_one(sorted(e.user_name for e in ranked if e.cold_streak == max_cold), feature_count)],
            length=max_cold,
        )
        if max_cold >= STREAK_MIN
        else None
    )

    # --- Clueless (worst on the day) — last, so its scapegoat spreads away from
    # the picks/streak winners already recorded in ``feature_count``.
    clueless = _clueless_stat(
        daily_points, names, reference=reference, feature_count=feature_count
    )

    return DropPayload(
        leader=leader,
        mover=mover,
        faceplant=faceplant,
        points_haul=points_haul,
        wooden_spoon=wooden_spoon,
        clueless=clueless,
        called_it=called_it,
        contrarian=contrarian,
        blunder=blunder,
        hottest_streak=hottest_streak,
        coldest_streak=coldest_streak,
        match_count=match_count,
        player_count=len(ranked),
    )


async def _todays_match_results(
    session: AsyncSession, user_id: uuid.UUID, *, since: datetime, until: datetime
) -> list[MatchResult]:
    """The viewer's performance on every match that FINISHED in the drop window
    (kickoff in ``[since, until]``): their pick vs the result, points won, and a
    coarse exact/outcome/miss flag.

    This powers the per-match "Your Day" recap — informative even on a 0-point
    day (the bug this replaced showed cumulative season-to-date category totals,
    then hid the row entirely when the day's haul was zero, so a rough day looked
    like a broken page). Match-derived only: advancement / bonus payouts aren't
    tied to a match finishing in the window. ``until`` anchors the window to the
    drop (the 24h before the morning build), not the viewer's clock.
    """
    # Local import: scoring pulls in the config + bonus layers; importing at
    # module load would widen this service's import graph.
    from app.services.scoring import calculate_match_points, get_outcome_counts

    rows = (
        await session.execute(
            select(MatchPrediction, Score, Fixture)
            .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
            .join(Score, Score.fixture_id == Fixture.id)
            .where(
                MatchPrediction.user_id == user_id,
                Fixture.status == MatchStatus.FINISHED,
                Fixture.kickoff >= since,
                Fixture.kickoff <= until,
            )
            .order_by(Fixture.kickoff)
        )
    ).all()

    results: list[MatchResult] = []
    for prediction, score, fixture in rows:
        counts = await get_outcome_counts(session, fixture.id)
        total_predictors = sum(counts.values())
        correct_predictors = counts.get(score.outcome, 0)
        points, is_correct_outcome, is_exact_score = calculate_match_points(
            prediction, score,
            total_predictors=total_predictors,
            correct_predictors=correct_predictors,
        )
        results.append(MatchResult(
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            predicted=f"{prediction.home_score}-{prediction.away_score}",
            actual=f"{score.final_home_score}-{score.final_away_score}",
            points=points,
            result="exact" if is_exact_score else "outcome" if is_correct_outcome else "miss",
        ))
    return results


async def compute_personal_stats(
    session: AsyncSession, user_id: uuid.UUID, *, reference: datetime | None = None
) -> PersonalStats | None:
    """The VIEWER's own day, for the personalised "Your Day" page. Returns None
    if the viewer isn't a ranked player (anonymous/ghost/inactive)."""
    board = await calculate_leaderboard(session)
    entry = next(
        (e for e in board.entries if e.user_id == user_id and not e.is_ghost), None
    )
    if entry is None:
        return None

    # "Your Day" performance: the matches in the drop window and how the viewer
    # did on each. The window is anchored to the drop (``reference`` = the morning
    # build) and spans the 24h before it — "your last 24 hours" — NOT the viewer's
    # clock at open-time. The day's haul is the sum of these match points.
    until = reference or utc_now()
    since = until - timedelta(hours=WINDOW_HOURS)
    match_results = await _todays_match_results(session, user_id, since=since, until=until)
    points_gained: int | None = sum(m.points for m in match_results) or None

    return PersonalStats(
        user_name=entry.user_name,
        position=entry.position,
        movement=entry.movement,
        points=entry.total_points,
        points_gained=points_gained,
        hot_streak=entry.hot_streak,
        cold_streak=entry.cold_streak,
        match_results=match_results,
    )


def _fmt_names(names: list[str]) -> str:
    """Overflow formatting for a tied set: 'A' · 'A & B' · 'A, B & C' · 'A, B +N'."""
    n = len(names)
    if n == 0:
        return "Nobody"
    if n == 1:
        return names[0]
    if n == 2:
        return f"{names[0]} & {names[1]}"
    if n == 3:
        return f"{names[0]}, {names[1]} & {names[2]}"
    return f"{names[0]}, {names[1]} +{n - 2}"


def placeholder_roast(p: DropPayload) -> str:
    """A deterministic stand-in roast assembled from the day's stats.

    Used purely to VISUALISE the card until Phase C swaps in the real thing —
    Claude writing it on the user's Claude Code subscription. It is never stored
    (synthesised at response time when ``roast`` is null), so the genuine roast
    can take its place cleanly. Intentionally template-y and tame; the real one
    will be far nastier and reference the dossiers.
    """
    bits: list[str] = []
    if p.blunder:
        bits.append(
            f"{_fmt_names(p.blunder.names)} looked at {p.blunder.home_team} v "
            f"{p.blunder.away_team}, confidently scribbled {p.blunder.predicted}, "
            f"and watched it finish {p.blunder.actual}. Frame it."
        )
    if p.coldest_streak:
        bits.append(
            f"{_fmt_names(p.coldest_streak.names)} — wrong "
            f"{p.coldest_streak.length} times on the bounce, a cold streak so "
            f"pure it belongs in a museum."
        )
    if p.wooden_spoon:
        bits.append(
            f"Propping up the whole table: {_fmt_names(p.wooden_spoon.names)}, "
            f"{p.wooden_spoon.behind_leader} points adrift and showing no pulse."
        )
    if p.called_it:
        bits.append(
            f"The one bright spark — {_fmt_names(p.called_it.names)} nailed "
            f"{p.called_it.home_team} {p.called_it.home_score}-"
            f"{p.called_it.away_score} {p.called_it.away_team} when nobody else dared."
        )
    if p.leader:
        bits.append(
            f"And {_fmt_names(p.leader.names)} struts on top by {p.leader.lead}. "
            f"Enjoy it while it lasts."
        )
    if not bits:
        return (
            "Quiet one today — nobody embarrassed themselves quite enough to earn "
            "a proper roasting. Yet."
        )
    return " ".join(bits)


# Hard ceiling on roast generation from the build path. ``generate_roast`` already
# fails soft, but a roaster that *hangs* (vs fast-fails) could otherwise hold the
# single-threaded scheduler loop for minutes (3× the httpx timeout). This caps it:
# once-daily call, so a generous bound is fine; on timeout → placeholder.
_ROAST_BUILD_TIMEOUT_S = 240


async def _capped_roast(payload: DropPayload, past_roasts: list[str]) -> str | None:
    try:
        return await asyncio.wait_for(
            generate_roast(payload, past_roasts), _ROAST_BUILD_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        return None


async def build_daily_drop(
    session: AsyncSession, *, drop_date: date | None = None, force: bool = False
) -> DailyDrop:
    """Upsert today's Drop row. Idempotent: if a row for ``drop_date`` already
    exists it is returned untouched unless ``force`` recomputes the payload
    (the roast is always preserved across a recompute)."""
    drop_date = drop_date or utc_now().date()

    existing = (
        await session.execute(select(DailyDrop).where(DailyDrop.drop_date == drop_date))
    ).scalar_one_or_none()
    if existing is not None and not force:
        return existing

    payload = await compute_drop_payload(session)
    payload_json = payload.model_dump(mode="json")

    # The whole-tournament roast log (oldest first), so generation never repeats a
    # joke. Excludes today's own row so a force-rebuild doesn't see itself.
    past_roasts = list(
        (
            await session.execute(
                select(DailyDrop.roast)
                .where(DailyDrop.roast.is_not(None), DailyDrop.drop_date != drop_date)
                .order_by(DailyDrop.drop_date)
            )
        )
        .scalars()
        .all()
    )

    if existing is not None:
        existing.payload = payload_json  # a good roast is preserved across recompute
        if existing.roast is None:  # …but a missing one is (re)tried on force
            roast = await _capped_roast(payload, past_roasts)
            if roast:
                existing.roast = roast
                existing.roast_generated_at = utc_now()
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
        return existing

    drop = DailyDrop(drop_date=drop_date, payload=payload_json)
    roast = await _capped_roast(payload, past_roasts)
    if roast:
        drop.roast = roast
        drop.roast_generated_at = utc_now()
    session.add(drop)
    await session.commit()
    await session.refresh(drop)
    return drop
