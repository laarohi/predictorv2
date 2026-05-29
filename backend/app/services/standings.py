"""Standings calculation service.

Computes actual group standings from finished fixtures and scores.

Tiebreaker chain (FIFA World Cup 2026 Regulations, Article 13):

  Among teams equal on POINTS:
    Step 1 — head-to-head among the tied teams' mutual matches:
      a) H2H points (descending)
      b) H2H goal difference (descending)
      c) H2H goals scored (descending)
    Step 2 — if any subset remains tied after step 1:
      • Re-apply criteria a-c using ONLY the mutual matches of the still-
        tied subset (re-scoped H2H). If a tie still survives that:
      d) overall goal difference (descending)
      e) overall goals scored (descending)
      f) fair-play conduct score — we don't track yellow/red cards, so
         the chain emits a TieWarning here and proceeds to step 3.
      (FIFA's "second step does not restart" clause: once descended from
      step 1 to d/e/f, the chain does not loop back to H2H.)
    Step 3:
      g) most recent FIFA Ranking
      h) preceding FIFA Ranking editions
      For our purposes (g) and (h) collapse to "the FIFA Rankings list
      from YAML"; teams not on the list rank below teams on the list.
    Last resort:
      Alphabetical by team name (deterministic, only reached when FIFA
      Rankings cover none of the still-tied teams).

For the third-placed-teams ranking (cross-group), step 1 H2H is not
applicable (the teams come from different groups so they never met).
The chain collapses to: overall points → overall GD → overall GF →
fair-play (warn) → FIFA Rankings → alphabetical.

Every fair-play-tier descent emits a TieWarning so callers can surface
"this part of the order isn't fully FIFA-resolved — the official chain
would have needed conduct data we don't track" to the user.
"""

from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score


class TieWarning(TypedDict):
    """Indicates one set of teams whose tie required the alphabetical fallback.

    `context` distinguishes between in-group ranking ties (where H2H *was*
    attempted but couldn't separate the teams) and third-place qualifying
    ties (where H2H *isn't applicable* because the teams come from
    different groups).
    """

    group: str
    tied_teams: list[str]  # alphabetically sorted, for stable display
    context: str  # "group_standings" or "third_place_qualifying"


class TeamStanding:
    """Team standing in a group."""

    def __init__(self, team: str, group: str):
        self.team = team
        self.group = group
        self.played = 0
        self.won = 0
        self.drawn = 0
        self.lost = 0
        self.goals_for = 0
        self.goals_against = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def points(self) -> int:
        return self.won * 3 + self.drawn

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "team": self.team,
            "group": self.group,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "goal_difference": self.goal_difference,
            "points": self.points,
        }


# ---------------------------------------------------------------------------
# FIFA tiebreaker chain
# ---------------------------------------------------------------------------


def _apply_fifa_tiebreakers(
    teams: list[dict],
    *,
    group_matches: list[tuple[Fixture, Score]] | None = None,
    context: str,
    fifa_rankings: list[str] | None = None,
) -> tuple[list[dict], list[TieWarning]]:
    """Rank `teams` per FIFA WC 2026 Regulations Article 13.

    Args:
        teams: team standings dicts (must contain 'team', 'group', 'points',
            'goal_difference', 'goals_for').
        group_matches: (fixture, score) tuples used for the H2H step. Pass
            None or [] for cross-group sorts like the third-place ranking —
            Article 13 doesn't apply H2H across groups.
        context: tagged onto every TieWarning so callers can distinguish
            in-group vs third-place ties ('group_standings',
            'third_place_qualifying').
        fifa_rankings: ordered list of team names, position 0 = rank #1.
            Used by Step 3 g/h. Defaults to empty (falls through to
            alphabetical when ranking data isn't available).

    Returns (sorted_teams, warnings). Each fair-play-tier descent (where
    we'd need yellow/red-card data we don't track) emits one TieWarning
    naming the still-tied teams, even if FIFA Rankings then resolves them.
    """
    warnings: list[TieWarning] = []
    rankings = fifa_rankings if fifa_rankings is not None else []

    # Sort by overall points and walk segments tied on points only. Article
    # 13's step 1 ("equal on points → H2H") triggers on POINTS equality —
    # not on full (points, GD, GF) equality as the legacy implementation did.
    sorted_by_points = sorted(teams, key=lambda t: -t["points"])
    result: list[dict] = []
    i = 0
    while i < len(sorted_by_points):
        j = _segment_end(sorted_by_points, i, key=lambda t: t["points"])
        segment = sorted_by_points[i:j]
        if len(segment) == 1:
            result.append(segment[0])
        else:
            result.extend(
                _resolve_points_tied_subset(
                    segment, group_matches, context, rankings, warnings,
                )
            )
        i = j
    return result, warnings


def _segment_end(items: list[dict], start: int, *, key) -> int:
    """Return the first index `j` >= start+1 where the sort key changes."""
    base = key(items[start])
    j = start + 1
    while j < len(items) and key(items[j]) == base:
        j += 1
    return j


def _resolve_points_tied_subset(
    tied: list[dict],
    group_matches: list[tuple[Fixture, Score]] | None,
    context: str,
    fifa_rankings: list[str],
    warnings: list[TieWarning],
) -> list[dict]:
    """Article 13 Step 1 (H2H a-c) with the Step 2 "re-apply to remaining
    teams only" clause modelled as recursion: each still-tied subset
    re-scopes its own H2H stats to that subset's mutual matches.

    Drops to Step 2 d-f/g (`_resolve_step_2_overall`) when H2H fails to
    separate any team in the subset, or when no H2H matches are available
    (cross-group ranking).
    """
    if not group_matches:
        return _resolve_step_2_overall(tied, context, fifa_rankings, warnings)

    # H2H stats are recomputed at every recursion level over only the
    # current subset's mutual matches. This is what Article 13 Step 2's
    # "criteria a-c above are applied to the matches between the remaining
    # teams only" actually means in practice.
    h2h_stats = _compute_h2h_stats(tied, group_matches)
    sort_key = lambda t: (
        -h2h_stats[t["team"]]["points"],
        -h2h_stats[t["team"]]["goal_difference"],
        -h2h_stats[t["team"]]["goals_for"],
    )
    seg_key = lambda t: (
        h2h_stats[t["team"]]["points"],
        h2h_stats[t["team"]]["goal_difference"],
        h2h_stats[t["team"]]["goals_for"],
    )
    sorted_by_h2h = sorted(tied, key=sort_key)

    out: list[dict] = []
    i = 0
    while i < len(sorted_by_h2h):
        j = _segment_end(sorted_by_h2h, i, key=seg_key)
        segment = sorted_by_h2h[i:j]
        if len(segment) == 1:
            out.append(segment[0])
        elif len(segment) == len(tied):
            # H2H didn't separate anyone in this subset. The "does not
            # restart" clause: descend to Step 2; don't loop on H2H.
            out.extend(_resolve_step_2_overall(segment, context, fifa_rankings, warnings))
        else:
            # H2H separated some teams. For the still-tied subset, recurse:
            # the recursion recomputes H2H over only that subset's mutual
            # matches (Article 13 Step 2 first clause).
            out.extend(_resolve_points_tied_subset(
                segment, group_matches, context, fifa_rankings, warnings,
            ))
        i = j
    return out


def _resolve_step_2_overall(
    tied: list[dict],
    context: str,
    fifa_rankings: list[str],
    warnings: list[TieWarning],
) -> list[dict]:
    """Article 13 Step 2 d (overall GD) then e (overall GF). Any subset
    still tied after both descends to fair-play (warn) + Step 3."""
    return _walk_segments(
        tied,
        sort_key=lambda t: (-t["goal_difference"], -t["goals_for"]),
        seg_key=lambda t: t["goal_difference"],
        on_segment=lambda sub: _resolve_step_2e(sub, context, fifa_rankings, warnings),
    )


def _resolve_step_2e(
    tied: list[dict],
    context: str,
    fifa_rankings: list[str],
    warnings: list[TieWarning],
) -> list[dict]:
    """Article 13 Step 2 e (overall GF). Still tied → fair-play warn +
    Step 3 g (FIFA Rankings)."""
    return _walk_segments(
        tied,
        sort_key=lambda t: -t["goals_for"],
        seg_key=lambda t: t["goals_for"],
        on_segment=lambda sub: _resolve_fair_play_then_rankings(
            sub, context, fifa_rankings, warnings,
        ),
    )


def _resolve_fair_play_then_rankings(
    tied: list[dict],
    context: str,
    fifa_rankings: list[str],
    warnings: list[TieWarning],
) -> list[dict]:
    """Article 13 Step 2 f (fair-play, untracked → warn) + Step 3 g/h
    (FIFA Rankings). Listed teams rank above unlisted by ranking index;
    teams not in the rankings list fall to alphabetical."""
    warnings.append(
        TieWarning(
            group=tied[0].get("group", ""),
            tied_teams=sorted(t["team"] for t in tied),
            context=context,
        )
    )
    ranking_index = {team: i for i, team in enumerate(fifa_rankings)}
    not_listed = len(fifa_rankings) + 1  # any value larger than max listed index
    return sorted(
        tied,
        key=lambda t: (ranking_index.get(t["team"], not_listed), t["team"]),
    )


def _walk_segments(
    items: list[dict],
    *,
    sort_key,
    seg_key,
    on_segment,
) -> list[dict]:
    """Sort `items` by `sort_key`; for each maximal segment of items that
    share the same `seg_key`, call `on_segment(segment)` to resolve the
    sub-tie. Singletons pass through untouched."""
    sorted_items = sorted(items, key=sort_key)
    out: list[dict] = []
    i = 0
    while i < len(sorted_items):
        j = _segment_end(sorted_items, i, key=seg_key)
        segment = sorted_items[i:j]
        if len(segment) == 1:
            out.append(segment[0])
        else:
            out.extend(on_segment(segment))
        i = j
    return out


async def _resolve_fifa_rankings(session: AsyncSession) -> list[str]:
    """Load FIFA rankings from the `fifa_rankings` table. Async because
    it needs a session — called at the async boundary so the sync
    tiebreaker chain receives a plain list. Returns `[]` if the table
    hasn't been synced; the tiebreaker chain then falls through to
    alphabetical (which is the documented behavior when ranking data
    is unavailable)."""
    # Lazy import to avoid pulling the bonus service into the import
    # chain at module load — standings is imported from many places.
    from app.services.bonus import get_fifa_rankings
    return await get_fifa_rankings(session)


def _compute_h2h_stats(
    tied_teams: list[dict],
    matches: list[tuple[Fixture, Score]],
) -> dict[str, dict[str, int]]:
    """Build a mini-table of points/GD/goals from matches BETWEEN the tied teams only."""
    tied_names = {t["team"] for t in tied_teams}
    stats = {
        t["team"]: {"points": 0, "goal_difference": 0, "goals_for": 0}
        for t in tied_teams
    }

    for fixture, score in matches:
        if score is None:
            continue
        if fixture.home_team not in tied_names or fixture.away_team not in tied_names:
            continue

        home, away = fixture.home_team, fixture.away_team
        if score.home_score > score.away_score:
            stats[home]["points"] += 3
        elif score.home_score < score.away_score:
            stats[away]["points"] += 3
        else:
            stats[home]["points"] += 1
            stats[away]["points"] += 1
        stats[home]["goals_for"] += score.home_score
        stats[home]["goal_difference"] += score.home_score - score.away_score
        stats[away]["goals_for"] += score.away_score
        stats[away]["goal_difference"] += score.away_score - score.home_score

    return stats


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_actual_group_standings(
    session: AsyncSession,
) -> dict[str, list[dict]]:
    """Compute actual group standings from finished group stage fixtures."""
    standings, _warnings = await get_actual_group_standings_with_warnings(session)
    return standings


async def get_actual_group_standings_with_warnings(
    session: AsyncSession,
) -> tuple[dict[str, list[dict]], list[TieWarning]]:
    """Same as get_actual_group_standings but also returns alphabetical-tie warnings.

    Use this variant when surfacing the warnings to the user is important
    (e.g. the predictions wizard, or any UI that explains the standings).
    """
    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            Fixture.stage == "group",
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    # Build raw standings + collect per-group match lists for H2H lookup.
    standings_by_group: dict[str, dict[str, TeamStanding]] = {}
    matches_by_group: dict[str, list[tuple[Fixture, Score]]] = {}

    for fixture, score in rows:
        if not score or not fixture.group:
            continue
        group = fixture.group
        standings_by_group.setdefault(group, {})
        matches_by_group.setdefault(group, []).append((fixture, score))

        for name in (fixture.home_team, fixture.away_team):
            if name not in standings_by_group[group]:
                standings_by_group[group][name] = TeamStanding(name, group)

        home = standings_by_group[group][fixture.home_team]
        away = standings_by_group[group][fixture.away_team]

        home.played += 1
        away.played += 1
        home.goals_for += score.home_score
        home.goals_against += score.away_score
        away.goals_for += score.away_score
        away.goals_against += score.home_score

        if score.home_score > score.away_score:
            home.won += 1
            away.lost += 1
        elif score.home_score < score.away_score:
            away.won += 1
            home.lost += 1
        else:
            home.drawn += 1
            away.drawn += 1

    # Sort each group with FIFA tiebreakers and accumulate warnings.
    # Resolve rankings once at the async boundary so the (sync) tiebreaker
    # chain doesn't need a session.
    rankings = await _resolve_fifa_rankings(session)
    out_standings: dict[str, list[dict]] = {}
    out_warnings: list[TieWarning] = []
    for group, teams_dict in standings_by_group.items():
        teams = [t.to_dict() for t in teams_dict.values()]
        sorted_teams, warnings = _apply_fifa_tiebreakers(
            teams,
            group_matches=matches_by_group.get(group, []),
            context="group_standings",
            fifa_rankings=rankings,
        )
        out_standings[group] = sorted_teams
        out_warnings.extend(warnings)

    return out_standings, out_warnings


async def get_group_positions(session: AsyncSession) -> dict[str, str]:
    """Get team positions in each group (e.g., '1A' -> 'France')."""
    standings = await get_actual_group_standings(session)
    positions: dict[str, str] = {}
    for group, teams in standings.items():
        for i, team in enumerate(teams):
            positions[f"{i + 1}{group}"] = team["team"]
    return positions


async def get_qualifying_third_place_teams(
    session: AsyncSession,
) -> list[dict]:
    """Get the 8 best third-place teams that qualify for knockout stage."""
    qualifying, _warnings = await get_qualifying_third_place_teams_with_warnings(session)
    return qualifying


async def get_qualifying_third_place_teams_with_warnings(
    session: AsyncSession,
) -> tuple[list[dict], list[TieWarning]]:
    """Same as get_qualifying_third_place_teams but also returns warnings.

    Note: head-to-head isn't applicable here because the third-placed teams
    come from different groups — they never played each other. So any tie on
    points/GD/GF goes straight to alphabetical with a warning.
    """
    standings, group_warnings = await get_actual_group_standings_with_warnings(session)

    # Collect all third-place teams.
    third_place_teams = []
    for group, teams in standings.items():
        if len(teams) >= 3:
            third_place_teams.append({**teams[2], "group": group})

    rankings = await _resolve_fifa_rankings(session)
    sorted_third, third_warnings = _apply_fifa_tiebreakers(
        third_place_teams,
        group_matches=None,  # H2H not applicable cross-group
        context="third_place_qualifying",
        fifa_rankings=rankings,
    )

    # Top 8 qualify. Note: warnings about ties that straddle the 8/9 boundary
    # are particularly important — they affect who actually advances. Callers
    # see all warnings; surfacing logic decides which to display.
    return sorted_third[:8], group_warnings + third_warnings
