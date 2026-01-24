"""Fixtures API routes."""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from app.dependencies import AdminUser, DbSession, OptionalUser
from app.models.fixture import Fixture, MatchStatus
from app.schemas.fixture import (
    FixtureCreate,
    FixtureRead,
    FixturesByGroup,
    FixtureStatusUpdate,
    FixtureUpdate,
    LockStatus,
)

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


# Admin endpoints
@router.post("/", response_model=FixtureRead, status_code=status.HTTP_201_CREATED)
async def create_fixture(
    fixture_data: FixtureCreate,
    session: DbSession,
    _admin: AdminUser,
) -> FixtureRead:
    """Create a new fixture (admin only)."""
    fixture = Fixture(
        competition_id=fixture_data.competition_id,
        home_team=fixture_data.home_team,
        away_team=fixture_data.away_team,
        kickoff=fixture_data.kickoff,
        stage=fixture_data.stage,
        group=fixture_data.group,
        match_number=fixture_data.match_number,
        external_id=fixture_data.external_id,
        status=MatchStatus.SCHEDULED,
    )
    session.add(fixture)
    await session.commit()
    await session.refresh(fixture)
    return fixture_to_read(fixture)


@router.put("/{fixture_id}", response_model=FixtureRead)
async def update_fixture(
    fixture_id: uuid.UUID,
    fixture_data: FixtureUpdate,
    session: DbSession,
    _admin: AdminUser,
) -> FixtureRead:
    """Update a fixture (admin only)."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    update_data = fixture_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fixture, field, value)

    fixture.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(fixture)
    return fixture_to_read(fixture)


@router.patch("/{fixture_id}/status", response_model=FixtureRead)
async def update_fixture_status(
    fixture_id: uuid.UUID,
    status_data: FixtureStatusUpdate,
    session: DbSession,
    _admin: AdminUser,
) -> FixtureRead:
    """Update fixture status and minute (admin only)."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    fixture.status = status_data.status
    if status_data.minute is not None:
        fixture.minute = status_data.minute
    fixture.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(fixture)
    return fixture_to_read(fixture)


@router.delete("/{fixture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fixture(
    fixture_id: uuid.UUID,
    session: DbSession,
    _admin: AdminUser,
) -> None:
    """Delete a fixture (admin only)."""
    result = await session.execute(select(Fixture).where(Fixture.id == fixture_id))
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")

    await session.delete(fixture)
    await session.commit()
