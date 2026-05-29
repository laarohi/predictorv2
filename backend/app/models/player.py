"""Tournament squad players, populated by scripts/sync_squads.py.

Scraped from the Wikipedia "2026 FIFA World Cup squads" page. These rows
exist only to back the searchable player dropdowns for the award bonus
questions (Golden Ball / Boot / Boy / Glove) — both the user's pick and the
admin's correct answer select from this same canonical list, so the stored
`full_name` strings match exactly under the bonus scoring's normalized
comparison (see services/bonus.py). No foreign key into bonus_predictions is
needed for that reason.

The table is rebuilt wholesale on every sync (truncate + refill), the same
strategy as fifa_rankings: squads are still firming up (preliminary 55-man
lists trimming down to 26, a few teams not yet announced), so a clean replace
is simpler and self-healing versus reconciling stale rows.
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class Player(SQLModel, table=True):
    __tablename__ = "players"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # Display name as it appears on Wikipedia, accents preserved
    # (e.g. "Matěj Kovář"). This is the canonical value stored in
    # bonus_predictions.answer when picked from the dropdown.
    full_name: str = Field(index=True)
    # Surname / first name split from the row's `sortname=Surname, First`
    # parameter, which Wikipedia provides accent-stripped to ASCII. Used to
    # let the combobox match on surname alone ("mbappe" -> Kylian Mbappé).
    surname: str = Field(index=True)
    first_name: str = ""
    # Canonical DB team name (matches fixtures + fifa_codes), already mapped
    # from the Wikipedia section heading (e.g. "Czech Republic" -> "Czechia").
    country: str = Field(index=True)
    # FIFA 3-letter code for flag rendering; None if the country isn't in our
    # fifa_codes map.
    country_code: Optional[str] = Field(default=None, max_length=3)
    # GK | DF | MF | FW. Drives the Golden Glove (GK only) and Golden Boot
    # (non-GK) dropdown filters.
    position: str = Field(max_length=2)
    # Calendar date — a birthday has no timezone, so this is a plain `date`
    # column, deliberately NOT the system-wide TIMESTAMPTZ rule (which governs
    # instants like kickoffs/deadlines). Drives the Golden Boy U21 filter.
    # Nullable in case a squad row omits a parseable birth date.
    date_of_birth: Optional[date] = None
    synced_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
