"""Competition model for tournament configuration."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.fixture import Fixture
    from app.models.user import User


class Competition(SQLModel, table=True):
    """Competition instance (e.g., World Cup 2026)."""

    __tablename__ = "competitions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    entry_fee: Decimal = Field(default=Decimal("0.00"), max_digits=10, decimal_places=2)

    # Phase 1 Deadlines (Group Stage)
    phase1_deadline: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    # Phase 2 Control
    is_phase2_active: bool = Field(default=False)
    phase2_activated_at: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))
    phase2_bracket_deadline: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))
    phase2_deadline: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    # Configuration reference
    config_file: str | None = None

    # External API identifier (e.g. Football-Data competition code "WC")
    external_id: str | None = Field(default=None, index=True)

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    users: list["User"] = Relationship(back_populates="competition")
    fixtures: list["Fixture"] = Relationship(back_populates="competition")
