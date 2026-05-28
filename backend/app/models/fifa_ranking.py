"""FIFA world ranking snapshot, populated by scripts/sync_fifa_rankings.py."""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class FifaRanking(SQLModel, table=True):
    __tablename__ = "fifa_rankings"
    __table_args__ = (
        UniqueConstraint("country_code", name="uq_fifa_ranking_country_code"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    rank: int = Field(index=True)
    country_code: str = Field(max_length=3, index=True)
    team_name: str
    points: float
    pub_date: datetime = Field(sa_column=utc_datetime_column())
    synced_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
