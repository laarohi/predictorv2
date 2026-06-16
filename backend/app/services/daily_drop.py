"""Compute (and persist) the Daily Drop — the once-a-day broadcast banter card.

The card is BROADCAST (identical for everyone); the only per-user touch is the
morning push text, handled elsewhere. Everything here is derived from data that
already exists:

- **leader / wooden_spoon / hottest_streak / coldest_streak** — from the live
  ``calculate_leaderboard`` (which already carries hot/cold streaks).
- **mover / faceplant / points_haul** — from the diff between the two most
  recent ``LeaderboardSnapshot`` days (overnight movement).
- **called_it / contrarian / blunder** — from predictions joined to scores for
  matches that finished in the recent window.

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

# A finished match counts toward the "picks" stats if it kicked off within this
# many hours of the reference time. ~30h comfortably covers the prior day's
# evening slate when the drop is built the next morning, without dragging in
# matches already covered by an earlier drop.
PICKS_WINDOW_HOURS = 30

# The "Your Day" personal recap covers the 24h before the morning drop — "your
# last 24 hours". Anchored to the drop's build time, not the viewer's clock.
PERSONAL_WINDOW_HOURS = 24

# A streak only earns a card slot once it's actually a streak (matches the
# leaderboard chip's STREAK_MIN).
STREAK_MIN = 2


def _pick_one(candidates: list[str], feature_count: dict[str, int]) -> str:
    """Each picks-page award shows ONE player. When several tie, give it to the
    one featured fewest times so far (alphabetical tiebreak) so the awards spread
    across the group instead of one person sweeping the page. Records the pick."""
    winner = min(sorted(candidates), key=lambda n: feature_count.get(n, 0))
    feature_count[winner] = feature_count.get(winner, 0) + 1
    return winner


async def _snapshot_pair_dates(session: AsyncSession) -> tuple[date, date] | None:
    """The two most recent distinct snapshot days (latest, previous), or None
    if fewer than two days have been captured (→ no overnight movement yet)."""
    result = await session.execute(
        select(LeaderboardSnapshot.captured_date)
        .distinct()
        .order_by(LeaderboardSnapshot.captured_date.desc())
    )
    dates = [d for (d,) in result.all()]
    if len(dates) < 2:
        return None
    return dates[0], dates[1]


async def _positions_at(
    session: AsyncSession, captured: date
) -> dict[uuid.UUID, tuple[int, int]]:
    """user_id → (position, total_points) snapshot for one captured day."""
    result = await session.execute(
        select(
            LeaderboardSnapshot.user_id,
            LeaderboardSnapshot.position,
            LeaderboardSnapshot.total_points,
        ).where(LeaderboardSnapshot.captured_date == captured)
    )
    return {uid: (pos, pts) for uid, pos, pts in result.all()}


async def _movement_stats(
    session: AsyncSession, ghost_ids: set[uuid.UUID], names: dict[uuid.UUID, str]
) -> tuple[MoveStat | None, MoveStat | None, PointsHaulStat | None]:
    """mover / faceplant / points_haul from the last two snapshot days."""
    pair = await _snapshot_pair_dates(session)
    if pair is None:
        return None, None, None
    latest_d, prev_d = pair
    latest = await _positions_at(session, latest_d)
    prev = await _positions_at(session, prev_d)

    # Only users present on BOTH days and not ghosts can have "movement".
    uids = [u for u in latest if u in prev and u not in ghost_ids]
    if not uids:
        return None, None, None

    def climb(u: uuid.UUID) -> int:
        return prev[u][0] - latest[u][0]  # +ve = moved up the table

    def gain(u: uuid.UUID) -> int:
        return latest[u][1] - prev[u][1]

    def names_where(value: int, fn) -> list[str]:
        """All tied players whose metric equals ``value``, name-sorted."""
        return sorted(names.get(u, "?") for u in uids if fn(u) == value)

    max_climb = max(climb(u) for u in uids)
    min_climb = min(climb(u) for u in uids)
    max_gain = max(gain(u) for u in uids)

    mover = (
        MoveStat(names=names_where(max_climb, climb), delta=max_climb)
        if max_climb > 0 else None
    )
    faceplant = (
        MoveStat(names=names_where(min_climb, climb), delta=min_climb)
        if min_climb < 0 else None
    )
    points_haul = (
        PointsHaulStat(names=names_where(max_gain, gain), points_gained=max_gain)
        if max_gain > 0 else None
    )
    return mover, faceplant, points_haul


async def _pick_stats(
    session: AsyncSession, *, since: datetime, feature_count: dict[str, int]
) -> tuple[CalledItStat | None, ContrarianStat | None, BlunderStat | None, int]:
    """called_it / hipster / blunder over real players' picks on matches that
    finished with kickoff >= ``since``. ONE winner per award (least-featured
    tiebreak via ``feature_count``). Returns the stats + the match count."""
    result = await session.execute(
        select(Fixture, Score, MatchPrediction, User)
        .join(Score, Score.fixture_id == Fixture.id)
        .join(MatchPrediction, MatchPrediction.fixture_id == Fixture.id)
        .join(User, User.id == MatchPrediction.user_id)
        .where(Fixture.status == MatchStatus.FINISHED)
        .where(Fixture.kickoff >= since)
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
    """Compute the full broadcast card from current standings, the snapshot
    diff, and recent picks. Pure read — persists nothing."""
    reference = reference or utc_now()

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

    # --- Movement (snapshot diff) ----------------------------------------
    mover, faceplant, points_haul = await _movement_stats(session, ghost_ids, names)

    # --- Picks (recent finished matches) — ONE winner per award, spread by
    # least-featured across blunder → called_it → hipster → hottest → coldest.
    feature_count: dict[str, int] = {}
    since = reference - timedelta(hours=PICKS_WINDOW_HOURS)
    called_it, contrarian, blunder, match_count = await _pick_stats(
        session, since=since, feature_count=feature_count
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

    return DropPayload(
        leader=leader,
        mover=mover,
        faceplant=faceplant,
        points_haul=points_haul,
        wooden_spoon=wooden_spoon,
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
    since = until - timedelta(hours=PERSONAL_WINDOW_HOURS)
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
_ROAST_BUILD_TIMEOUT_S = 120


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
