from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Match:
    match_time: datetime
    league: str
    home_team: str
    away_team: str
    home_odds: float | None = None
    draw_odds: float | None = None
    away_odds: float | None = None
    asian_line: float | None = None
    asian_home_odds: float | None = None
    asian_away_odds: float | None = None
    total_line: float | None = None
    over_odds: float | None = None
    under_odds: float | None = None
    source: str = ""
    updated_at: datetime | None = None
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Prediction:
    home: float
    draw: float
    away: float
    result: str
    confidence: float
    analyzed_at: datetime
