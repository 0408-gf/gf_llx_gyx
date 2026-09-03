from __future__ import annotations

import json
import sqlite3
import hashlib
from datetime import datetime, timezone
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
        CREATE TABLE IF NOT EXISTS provider_snapshots(
            id INTEGER PRIMARY KEY, provider TEXT NOT NULL, external_id TEXT NOT NULL, fetched_at TEXT NOT NULL,
            provider_updated_at TEXT, payload_hash TEXT NOT NULL, kickoff_utc TEXT NOT NULL, league TEXT NOT NULL,
            home_team TEXT NOT NULL, away_team TEXT NOT NULL, status TEXT, home_score INTEGER, away_score INTEGER,
            odds_json TEXT NOT NULL, raw_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_provider_snapshot_lookup ON provider_snapshots(provider, external_id, fetched_at);
        CREATE TABLE IF NOT EXISTS external_mappings(
            primary_provider TEXT NOT NULL, primary_external_id TEXT NOT NULL, secondary_provider TEXT,
            secondary_external_id TEXT, local_match_id INTEGER, confirmed_at TEXT NOT NULL,
            PRIMARY KEY(primary_provider, primary_external_id), FOREIGN KEY(local_match_id) REFERENCES matches(id));
        CREATE TABLE IF NOT EXISTS sync_runs(
            id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, trigger TEXT NOT NULL,
            status TEXT NOT NULL, primary_count INTEGER DEFAULT 0, secondary_count INTEGER DEFAULT 0, message TEXT);
        CREATE TABLE IF NOT EXISTS sync_conflicts(
            id INTEGER PRIMARY KEY, sync_run_id INTEGER NOT NULL, primary_external_id TEXT, secondary_external_id TEXT,
            kind TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(sync_run_id) REFERENCES sync_runs(id));
        """)
        self.connection.commit()

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

    def start_sync_run(self, trigger: str) -> int:
        cursor = self.connection.execute("INSERT INTO sync_runs(started_at,trigger,status) VALUES (?,?,?)",
                                         (datetime.now(timezone.utc).isoformat(), trigger, "运行中"))
        self.connection.commit(); return int(cursor.lastrowid)

    def finish_sync_run(self, run_id: int, status: str, primary_count: int, secondary_count: int, message: str = "") -> None:
        self.connection.execute("UPDATE sync_runs SET finished_at=?,status=?,primary_count=?,secondary_count=?,message=? WHERE id=?",
                                (datetime.now(timezone.utc).isoformat(), status, primary_count, secondary_count, message, run_id))
        self.connection.commit()

    def save_provider_snapshots(self, matches: list[object], fetched_at: datetime | None = None) -> None:
        fetched = (fetched_at or datetime.now(timezone.utc)).isoformat()
        for match in matches:
            raw_json = json.dumps(match.raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self.connection.execute("""INSERT INTO provider_snapshots(
                provider,external_id,fetched_at,provider_updated_at,payload_hash,kickoff_utc,league,home_team,away_team,
                status,home_score,away_score,odds_json,raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (match.provider, match.external_id, fetched, match.provider_updated_at.isoformat() if match.provider_updated_at else None,
                 hashlib.sha256(raw_json.encode()).hexdigest(), match.kickoff_utc.isoformat(), match.league, match.home_team,
                 match.away_team, match.status, match.home_score, match.away_score,
                 json.dumps(match.odds, ensure_ascii=False), raw_json))
        self.connection.commit()

    def latest_provider_snapshots(self, provider: str | None = None) -> list[sqlite3.Row]:
        where, params = ("WHERE s.provider=?", (provider,)) if provider else ("", ())
        return list(self.connection.execute(f"""SELECT s.* FROM provider_snapshots s JOIN (
            SELECT provider,external_id,MAX(id) id FROM provider_snapshots GROUP BY provider,external_id
        ) latest ON latest.id=s.id {where} ORDER BY s.kickoff_utc""", params))

    def stable_provider_mappings(self) -> dict[str, str]:
        return {row[0]: row[1] for row in self.connection.execute(
            "SELECT primary_external_id,secondary_external_id FROM external_mappings WHERE secondary_external_id IS NOT NULL")}

    def save_external_mapping(self, primary_id: str, secondary_id: str | None, local_match_id: int | None = None) -> None:
        self.connection.execute("""INSERT INTO external_mappings(primary_provider,primary_external_id,secondary_provider,
            secondary_external_id,local_match_id,confirmed_at) VALUES ('API-Football',?,'football-data.org',?,?,?)
            ON CONFLICT(primary_provider,primary_external_id) DO UPDATE SET secondary_external_id=excluded.secondary_external_id,
            local_match_id=COALESCE(excluded.local_match_id,external_mappings.local_match_id),confirmed_at=excluded.confirmed_at""",
            (primary_id, secondary_id, local_match_id, datetime.now(timezone.utc).isoformat()))
        self.connection.commit()

    def save_sync_conflict(self, run_id: int, primary_id: str | None, secondary_id: str | None, kind: str, details: str) -> None:
        self.connection.execute("INSERT INTO sync_conflicts(sync_run_id,primary_external_id,secondary_external_id,kind,details,created_at) VALUES (?,?,?,?,?,?)",
                                (run_id, primary_id, secondary_id, kind, details, datetime.now(timezone.utc).isoformat()))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
