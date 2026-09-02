from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ProviderMatch:
    provider: str
    external_id: str
    kickoff_utc: datetime
    league: str
    home_team: str
    away_team: str
    status: str
    home_score: int | None = None
    away_score: int | None = None
    provider_updated_at: datetime | None = None
    odds: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerifiedMatch:
    primary: ProviderMatch | None
    secondary: ProviderMatch | None
    verification: str
    details: str = ""
    stale: bool = False

