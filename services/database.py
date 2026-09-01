from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from models.match import Match, Prediction
from services.paths import default_database_path


class Database:
    def __init__(self, path: str | Path | None = None):
        path = default_database_path() if path is None else Path(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._schema()

    def _schema(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY, match_time TEXT NOT NULL, league TEXT NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL, home_odds REAL, draw_odds REAL, away_odds REAL, asian_line REAL, asian_home_odds REAL, asian_away_odds REAL, total_line REAL, over_odds REAL, under_odds REAL, source TEXT NOT NULL, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, analyzed_at TEXT NOT NULL, FOREIGN KEY(match_id) REFERENCES matches(id));
        CREATE TABLE IF NOT EXISTS ev_results(id INTEGER PRIMARY KEY, match_id INTEGER NOT NULL, selection TEXT NOT NULL, probability REAL NOT NULL, odds REAL NOT NULL, ev REAL NOT NULL, analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(match_id) REFERENCES matches(id));
        CREATE TABLE IF NOT EXISTS betting_combinations(id INTEGER PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS bankroll_records(id INTEGER PRIMARY KEY, bankroll REAL NOT NULL, stake REAL NOT NULL, method TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)

    def add_matches(self, matches: list[Match]) -> int:
        sql = "INSERT INTO matches(match_time,league,home_team,away_team,home_odds,draw_odds,away_odds,asian_line,asian_home_odds,asian_away_odds,total_line,over_odds,under_odds,source,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        for m in matches:
            values = m.to_dict(); values.pop("id")
            for key in ("match_time", "updated_at"):
                values[key] = values[key].isoformat(sep=" ") if values[key] else None
            cur = self.connection.execute(sql, tuple(values.values())); m.id = cur.lastrowid
        self.connection.commit(); return len(matches)

    def list_matches(self) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM matches ORDER BY match_time"))

    def save_prediction(self, match_id: int, prediction: Prediction) -> None:
        payload = {"home": prediction.home, "draw": prediction.draw, "away": prediction.away, "result": prediction.result, "confidence": prediction.confidence}
        self.connection.execute("INSERT INTO analyses(match_id,kind,payload,analyzed_at) VALUES (?,?,?,?)", (match_id, "prediction", json.dumps(payload, ensure_ascii=False), prediction.analyzed_at.isoformat()))
        self.connection.commit()

    def list_predictions(self) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM analyses WHERE kind = 'prediction' ORDER BY analyzed_at"))

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
