from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Callable

from models.provider import ProviderMatch, VerifiedMatch
from services.credentials import CredentialStore
from services.database import Database
from services.providers import APIFootballProvider, FootballDataProvider, ProviderError, RateLimitError
from services.sync import verify_sources


class LiveSyncService:
    def __init__(self, database: Database, credentials: CredentialStore | None = None,
                 primary_factory: Callable[..., APIFootballProvider] = APIFootballProvider,
                 secondary_factory: Callable[..., FootballDataProvider] = FootballDataProvider) -> None:
        self.database = database; self.credentials = credentials or CredentialStore()
        self.primary_factory = primary_factory; self.secondary_factory = secondary_factory
        self.last_quota: dict[str, dict[str, str]] = {}

    def sync(self, day: date, live: bool = False, include_secondary: bool = True,
             trigger: str = "手动") -> tuple[list[VerifiedMatch], str | None]:
        primary_key = self.credentials.get("api-football")
        secondary_key = self.credentials.get("football-data") if include_secondary else None
        if not primary_key:
            raise ProviderError("尚未配置 API-Football Key；请在系统设置中自行注册并保存凭据。")
        if include_secondary and not secondary_key:
            raise ProviderError("尚未配置 football-data.org Key；请在系统设置中自行注册并保存凭据。")
        run_id = self.database.start_sync_run(trigger)
        primary: list[ProviderMatch] = []; secondary: list[ProviderMatch] = []
        try:
            primary_client = self.primary_factory(primary_key); primary = primary_client.matches(day, live)
            self.last_quota[primary_client.name] = primary_client.last_quota
            if include_secondary:
                secondary_client = self.secondary_factory(secondary_key)
                secondary = secondary_client.matches(day)
                self.last_quota[secondary_client.name] = secondary_client.last_quota
            else:
                secondary = [self._from_row(row) for row in self.database.latest_provider_snapshots("football-data.org")]
            self.database.save_provider_snapshots(primary + (secondary if include_secondary else []))
            verified = verify_sources(primary, secondary, self.database.stable_provider_mappings())
            for item in verified:
                if "冲突" in item.verification:
                    self.database.save_sync_conflict(run_id, item.primary.external_id if item.primary else None,
                                                     item.secondary.external_id if item.secondary else None,
                                                     item.verification, item.details)
            self.database.finish_sync_run(run_id, "成功", len(primary), len(secondary))
            return verified, None
        except ProviderError as exc:
            self.database.finish_sync_run(run_id, "失败", len(primary), len(secondary), str(exc))
            if isinstance(exc, RateLimitError):
                raise
            cached = self.cached_verified()
            if cached:
                return cached, f"{exc} 当前显示最后缓存，数据截至 {self.cache_time() or '未知时间'}。"
            raise

    def cached_verified(self) -> list[VerifiedMatch]:
        rows = self.database.latest_provider_snapshots()
        primary = [self._from_row(row) for row in rows if row["provider"] == "API-Football"]
        secondary = [self._from_row(row) for row in rows if row["provider"] == "football-data.org"]
        return verify_sources(primary, secondary, self.database.stable_provider_mappings())

    def cache_time(self) -> str | None:
        rows = self.database.latest_provider_snapshots()
        return max((row["fetched_at"] for row in rows), default=None)

    @staticmethod
    def _from_row(row: object) -> ProviderMatch:
        return ProviderMatch(row["provider"], row["external_id"], datetime.fromisoformat(row["kickoff_utc"]),
                             row["league"], row["home_team"], row["away_team"], row["status"] or "",
                             row["home_score"], row["away_score"],
                             datetime.fromisoformat(row["provider_updated_at"]) if row["provider_updated_at"] else None,
                             json.loads(row["odds_json"]), json.loads(row["raw_json"]))
