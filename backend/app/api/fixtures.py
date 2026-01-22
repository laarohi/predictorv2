"""Fixtures API routes."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.dependencies import DbSession, OptionalUser
from app.models.fixture import Fixture
from app.schemas.fixture import FixtureRead, FixturesByGroup, LockStatus

router = APIRouter()

LOCK_MINUTES = 5


def fixture_to_read(fixture: Fixture) -> FixtureRead:
    """Convert Fixture model to FixtureRead schema."""
    time_until = fixture.time_until_lock(LOCK_MINUTES)
    return FixtureRead(
        id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff=fixture.kickoff,
        stage=fixture.stage,
        group=fixture.group,
        match_number=fixture.match_number,
        status=fixture.status,
        minute=fixture.minute,
        is_locked=fixture.is_locked(LOCK_MINUTES),
        time_until_lock=int(time_until.total_seconds()) if time_until else None,
    )


@router.get("/", response_model=list[FixtureRead])
async def get_all_fixtures(session: DbSession, _user: OptionalUser) -> list[FixtureRead]:
    """Get all fixtures ordered by kickoff time."""
    result = await session.execute(select(Fixture).order_by(Fixture.kickoff, Fixture.match_number))
    fixtures = result.scalars().all()
    return [fixture_to_read(f) for f in fixtures]


@router.get("/groups", response_model=list[FixturesByGroup])
async def get_group_fixtures(session: DbSession, _user: OptionalUser) -> list[FixturesByGroup]:
    """Get group stage fixtures organized by group."""
    result = await session.execute(
        select(Fixture)
        .where(Fixture.stage == "group")
        .order_by(Fixture.group, Fixture.kickoff, Fixture.match_number)
    )
    fixtures = result.scalars().all()

    # Organize by group
    groups: dict[str, list[FixtureRead]] = {}
    for fixture in fixtures:
        group = fixture.group or "Unknown"
        if group not in groups:
            groups[group] = []
        groups[group].append(fixture_to_read(fixture))

    return [FixturesByGroup(group=g, fixtures=f) for g, f in sorted(groups.items())]


@router.get("/knockout", response_model=list[FixtureRead])
async def get_knockout_fixtures(session: DbSession, _user: OptionalUser) -> list[FixtureRead]:
    """Get knockout stage fixtures."""
    result = await session.execute(
        select(Fixture)
        .where(Fixture.stage != "group")
        .order_by(Fixture.kickoff, Fixture.match_number)
    )
    fixtures = result.scalars().all()
    return [fixture_to_read(f) for f in fixtures]


@router.get("/{fixture_id}", response_model=FixtureRead)
async def get_fixture(fixture_id: uuid.UUID, session: DbSession, _user: OptionalUser) -> FixtureRead:
    """Get a single fixture by ID."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    return fixture_to_read(fixture)


@router.get("/{fixture_id}/lock-status", response_model=LockStatus)
async def get_lock_status(
    fixture_id: uuid.UUID, session: DbSession, _user: OptionalUser
) -> LockStatus:
    """Check lock status for a fixture."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    locks_at = fixture.kickoff - timedelta(minutes=LOCK_MINUTES)

    return LockStatus(
        fixture_id=fixture.id,
        is_locked=fixture.is_locked(LOCK_MINUTES),
        locks_at=locks_at,
        time_remaining=fixture.time_until_lock(LOCK_MINUTES),
    )
