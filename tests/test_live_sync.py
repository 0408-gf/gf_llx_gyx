from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError

import pytest

from models.provider import ProviderMatch
from services.credentials import CredentialStore
from services.database import Database
from services.live_sync import LiveSyncService
from services.providers import (APIFootballProvider, AuthenticationError, FootballDataProvider,
                                ProviderError, RateLimitError)
from services.sync import normalize_name, verify_sources


NOW = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)


def _match(provider: str, external_id: str, home: str = "Alpha FC", away: str = "Beta",
           kickoff: datetime = NOW, score: tuple[int | None, int | None] = (None, None)) -> ProviderMatch:
    return ProviderMatch(provider, external_id, kickoff, "Test League", home, away, "SCHEDULED", score[0], score[1], NOW)


def _transport(status: int, payload: dict, headers: dict[str, str] | None = None):
    def call(request, timeout):
        assert request.full_url.startswith("https://")
        assert timeout == 12.0
        assert request.headers["User-agent"] == "FootballJCAssistant/0.1"
        return status, headers or {}, json.dumps(payload).encode()
    return call


def test_default_construction_makes_zero_network_calls(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr("services.providers.urlopen", lambda *args, **kwargs: calls.append(args))
    db = Database(tmp_path / "offline.db")
    LiveSyncService(db, CredentialStore(backend=None))
    assert calls == []


def test_api_football_fixture_and_odds_parsing():
    fixture = {"response": [{"fixture": {"id": 10, "date": "2026-09-02T12:00:00Z", "status": {"short": "1H"}, "update": "2026-09-02T12:01:00Z"},
                             "league": {"name": "League"}, "teams": {"home": {"name": "A"}, "away": {"name": "B"}}, "goals": {"home": 1, "away": 0}}]}
    odds = {"response": [{"fixture": {"id": 10}, "update": "2026-09-02T11:55:00Z", "bookmakers": [{"name": "Book A", "bets": [{"name": "Match Winner", "values": [{"value": "Home", "odd": "2.1"}]}]}]}]}
    responses = iter([_transport(200, fixture), _transport(200, odds)])
    provider = APIFootballProvider("secret", transport=lambda request, timeout: next(responses)(request, timeout))
    result = provider.matches(date(2026, 9, 2))[0]
    assert result.kickoff_utc.tzinfo == timezone.utc
    assert result.status == "1H" and result.home_score == 1
    assert result.odds[0] == {"bookmaker": "Book A", "market": "Match Winner", "selection": "Home", "odds": "2.1", "handicap": None, "provider_updated_at": "2026-09-02T11:55:00Z"}


def test_football_data_parsing_has_no_odds():
    payload = {"matches": [{"id": 20, "utcDate": "2026-09-02T12:00:00Z", "status": "FINISHED", "lastUpdated": "2026-09-02T14:00:00Z",
                            "competition": {"name": "League"}, "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}, "score": {"fullTime": {"home": 2, "away": 1}}}]}
    result = FootballDataProvider("secret", transport=_transport(200, payload)).matches(date(2026, 9, 2))[0]
    assert (result.home_score, result.away_score, result.odds) == (2, 1, [])


def test_conservative_verification_consistent_conflict_and_ambiguous():
    primary = _match("API-Football", "1", score=(1, 0))
    same = _match("football-data.org", "2", home="Alpha", score=(1, 0))
    assert verify_sources([primary], [same], now=NOW)[0].verification == "双源一致"
    conflict = _match("football-data.org", "3", home="Alpha", score=(0, 1))
    assert verify_sources([primary], [conflict], now=NOW)[0].verification == "冲突"
    ambiguous = verify_sources([primary], [same, _match("football-data.org", "4", home="Alpha")], now=NOW)[0]
    assert ambiguous.verification == "冲突/待人工确认" and ambiguous.secondary is None
    assert normalize_name("Alpha Football Club") == normalize_name("alpha")


def test_time_outside_tolerance_is_not_merged():
    result = verify_sources([_match("API-Football", "1")], [_match("football-data.org", "2", home="Alpha", kickoff=NOW + timedelta(minutes=16))], now=NOW)
    assert [item.verification for item in result] == ["仅主源", "仅复核源"]


@pytest.mark.parametrize("status,error", [(401, AuthenticationError), (429, RateLimitError)])
def test_auth_and_rate_limit_errors(status, error):
    sleeps = []
    provider = FootballDataProvider("not-logged", transport=_transport(status, {}), sleep=sleeps.append)
    with pytest.raises(error): provider.request("/matches")
    assert len(sleeps) <= 2


def test_timeout_retries_are_bounded():
    calls = []
    def timeout(request, seconds): calls.append(1); raise URLError("offline")
    with pytest.raises(ProviderError, match="请求超时"):
        FootballDataProvider("secret", transport=timeout, sleep=lambda seconds: None).request("/matches")
    assert len(calls) == 3


def test_429_honors_retry_after_but_has_retry_limit():
    calls = []; sleeps = []
    def limited(request, timeout): calls.append(1); return 429, {"Retry-After": "7"}, b"{}"
    with pytest.raises(RateLimitError):
        FootballDataProvider("secret", transport=limited, sleep=sleeps.append).request("/matches")
    assert calls == [1, 1, 1] and sleeps == [7.0, 7.0]


def test_5xx_retry_then_success_and_quota():
    responses = iter([(503, {}, b"{}"), (200, {"X-Requests-Remaining": "9"}, b"{}")]); sleeps = []
    provider = FootballDataProvider("secret", transport=lambda request, timeout: next(responses), sleep=sleeps.append)
    assert provider.request("/matches") == {}
    assert sleeps == [1] and provider.last_quota["x-requests-remaining"] == "9"


class FakeKeyring:
    def __init__(self, fail=False): self.values = {}; self.fail = fail
    def get_password(self, service, user):
        if self.fail: raise RuntimeError("backend failure")
        return self.values.get(user)
    def set_password(self, service, user, password):
        if self.fail: raise RuntimeError("backend failure")
        self.values[user] = password
    def delete_password(self, service, user): self.values.pop(user, None)


def test_credentials_use_keyring_or_process_memory_only(tmp_path: Path):
    backend = FakeKeyring(); store = CredentialStore(backend); assert store.set("api-football", "top-secret")
    assert backend.values["api-football"] == "top-secret"
    fallback = CredentialStore(FakeKeyring(fail=True)); assert not fallback.set("football-data", "memory-secret")
    assert fallback.get("football-data") == "memory-secret"
    db = Database(tmp_path / "credentials.db"); db.close()
    assert b"top-secret" not in (tmp_path / "credentials.db").read_bytes()
    assert "memory-secret" not in Path("config.json").read_text(encoding="utf-8")


def test_database_migration_snapshot_mapping_and_audit(tmp_path: Path):
    path = tmp_path / "old.db"; db = Database(path)
    db.save_provider_snapshots([_match("API-Football", "1")], NOW)
    db.save_external_mapping("1", "2")
    run = db.start_sync_run("测试"); db.save_sync_conflict(run, "1", "2", "冲突", "比分不同"); db.finish_sync_run(run, "成功", 1, 1)
    db.close(); reopened = Database(path)
    assert reopened.latest_provider_snapshots()[0]["payload_hash"]
    assert reopened.stable_provider_mappings() == {"1": "2"}
    assert reopened.connection.execute("SELECT status FROM sync_runs").fetchone()[0] == "成功"


def test_cache_fallback_after_network_error(tmp_path: Path):
    db = Database(tmp_path / "cache.db"); db.save_provider_snapshots([_match("API-Football", "1")], NOW)
    keys = FakeKeyring(); keys.values = {"api-football": "a", "football-data": "b"}
    class FailedProvider:
        name = "API-Football"; last_quota = {}
        def __init__(self, key): pass
        def matches(self, day, live=False): raise ProviderError("offline")
    service = LiveSyncService(db, CredentialStore(keys), primary_factory=FailedProvider)
    rows, warning = service.sync(date(2026, 9, 2))
    assert rows[0].verification in {"仅主源", "过期"} and "显示最后缓存" in warning
