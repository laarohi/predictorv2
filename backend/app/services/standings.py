"""Standings calculation service.

Computes actual group standings from finished fixtures and scores.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.score import Score


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


async def get_actual_group_standings(
    session: AsyncSession,
) -> dict[str, list[dict]]:
    """Compute actual group standings from finished group stage fixtures.

    Returns:
        Dict mapping group letter to list of team standings, sorted by position.
    """
    # Get all finished group stage fixtures with their scores
    result = await session.execute(
        select(Fixture, Score)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            Fixture.stage == "group",
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    # Build standings by group
    standings_by_group: dict[str, dict[str, TeamStanding]] = {}

    for fixture, score in rows:
        if not score or not fixture.group:
            continue

        group = fixture.group

        # Initialize group dict if needed
        if group not in standings_by_group:
            standings_by_group[group] = {}

        # Initialize team standings if needed
        if fixture.home_team not in standings_by_group[group]:
            standings_by_group[group][fixture.home_team] = TeamStanding(
                fixture.home_team, group
            )
        if fixture.away_team not in standings_by_group[group]:
            standings_by_group[group][fixture.away_team] = TeamStanding(
                fixture.away_team, group
            )

        home = standings_by_group[group][fixture.home_team]
        away = standings_by_group[group][fixture.away_team]

        # Update played count
        home.played += 1
        away.played += 1

        # Update goals
        home.goals_for += score.home_score
        home.goals_against += score.away_score
        away.goals_for += score.away_score
        away.goals_against += score.home_score

        # Update W/D/L based on outcome
        if score.home_score > score.away_score:
            home.won += 1
            away.lost += 1
        elif score.home_score < score.away_score:
            away.won += 1
            home.lost += 1
        else:
            home.drawn += 1
            away.drawn += 1

    # Sort each group and convert to response format
    result_standings: dict[str, list[dict]] = {}

    for group, teams in standings_by_group.items():
        # Sort by: points, goal difference, goals for, then alphabetically
        sorted_teams = sorted(
            teams.values(),
            key=lambda t: (-t.points, -t.goal_difference, -t.goals_for, t.team),
        )
        result_standings[group] = [t.to_dict() for t in sorted_teams]

    return result_standings


async def get_group_positions(session: AsyncSession) -> dict[str, str]:
    """Get team positions in each group (e.g., '1A' -> 'France').

    Returns:
        Dict mapping position codes to team names.
    """
    standings = await get_actual_group_standings(session)
    positions: dict[str, str] = {}

    for group, teams in standings.items():
        for i, team in enumerate(teams):
            position = i + 1  # 1-indexed
            positions[f"{position}{group}"] = team["team"]

    return positions


async def get_qualifying_third_place_teams(
    session: AsyncSession,
) -> list[dict]:
    """Get the 8 best third-place teams that qualify for knockout stage.

    Returns:
        List of qualifying third-place teams, sorted by ranking.
    """
    standings = await get_actual_group_standings(session)

    # Collect all third-place teams
    third_place_teams = []
    for group, teams in standings.items():
        if len(teams) >= 3:
            third_place_teams.append({**teams[2], "group": group})

    # Sort by points, goal difference, goals for
    third_place_teams.sort(
        key=lambda t: (-t["points"], -t["goal_difference"], -t["goals_for"], t["team"]),
    )

    # Top 8 qualify
    return third_place_teams[:8]
