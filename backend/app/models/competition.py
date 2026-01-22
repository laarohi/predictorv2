"""Competition model for tournament configuration."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

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

    # Deadlines
    phase1_deadline: datetime | None = None  # Deadline for group predictions
    phase2_deadline: datetime | None = None  # Deadline for knockout predictions

    # Configuration reference
    config_file: str | None = None  # Path to YAML config

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    users: list["User"] = Relationship(back_populates="competition")
    fixtures: list["Fixture"] = Relationship(back_populates="competition")
