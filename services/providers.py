from __future__ import annotations

import json
import socket
import time
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from models.provider import ProviderMatch

Transport = Callable[[Request, float], tuple[int, dict[str, str], bytes]]


class ProviderError(RuntimeError):
    pass


class AuthenticationError(ProviderError):
    pass


class RateLimitError(ProviderError):
    pass


def _transport(request: Request, timeout: float) -> tuple[int, dict[str, str], bytes]:
    with urlopen(request, timeout=timeout) as response:
        return response.status, dict(response.headers.items()), response.read()


def _utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class Provider(ABC):
    name: str
    base_url: str

    def __init__(self, api_key: str, transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.api_key = api_key
        self.transport = transport or _transport
        self.sleep = sleep
        self.last_quota: dict[str, str] = {}

    @property
    @abstractmethod
    def auth_header(self) -> str: ...

    def request(self, path: str, params: dict[str, str] | None = None, retries: int = 2) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={self.auth_header: self.api_key, "User-Agent": "FootballJCAssistant/0.1", "Accept": "application/json"})
        for attempt in range(retries + 1):
            try:
                status, headers, body = self.transport(request, 12.0)
            except HTTPError as exc:
                status, headers, body = exc.code, dict(exc.headers.items()), exc.read()
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:
                if attempt < retries:
                    self.sleep(2 ** attempt); continue
                raise ProviderError("网络连接失败或请求超时；已保留本地缓存，请检查网络后手动重试。") from exc
            lower = {key.lower(): value for key, value in headers.items()}
            self.last_quota = {key: value for key, value in lower.items() if "ratelimit" in key or key.startswith("x-requests") or key == "x-requestcounter-reset"}
            if status in (401, 403):
                raise AuthenticationError(f"{self.name} 拒绝了 API Key；请检查凭据、订阅权限和请求域名。")
            if status == 429:
                if attempt >= retries:
                    raise RateLimitError(f"{self.name} 请求额度已用尽，自动刷新已暂停；请等待限额重置后再试。")
                delay = self._retry_after(lower.get("retry-after"), attempt)
                self.sleep(delay); continue
            if 500 <= status < 600:
                if attempt < retries:
                    self.sleep(2 ** attempt); continue
                raise ProviderError(f"{self.name} 服务暂时不可用（HTTP {status}）；已达到重试上限并保留缓存。")
            if status < 200 or status >= 300:
                raise ProviderError(f"{self.name} 请求失败（HTTP {status}），请稍后重试。")
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProviderError(f"{self.name} 返回了无法解析的数据。") from exc
            if isinstance(payload, dict) and payload.get("errors"):
                raise ProviderError(f"{self.name} 返回 API 错误；请检查 Key、套餐权限、请求额度和参数。")
            return payload
        raise ProviderError(f"{self.name} 请求失败。")

    @staticmethod
    def _retry_after(value: str | None, attempt: int) -> float:
        if value:
            try:
                return min(max(float(value), 0.0), 60.0)
            except ValueError:
                try:
                    return min(max((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds(), 0.0), 60.0)
                except (TypeError, ValueError):
                    pass
        return float(2 ** attempt)

    @abstractmethod
    def matches(self, day: date, live: bool = False) -> list[ProviderMatch]: ...

    def test_connection(self) -> None:
        self.matches(datetime.now(timezone.utc).date())


class APIFootballProvider(Provider):
    name = "API-Football"
    base_url = "https://v3.football.api-sports.io"
    auth_header = "x-apisports-key"

    def test_connection(self) -> None:
        self.request("/status")

    def matches(self, day: date, live: bool = False) -> list[ProviderMatch]:
        params = {"live": "all"} if live else {"date": day.isoformat(), "timezone": "UTC"}
        fixtures = self.request("/fixtures", params).get("response", [])
        odds_payload = self.request("/odds/live" if live else "/odds", {"date": day.isoformat()} if not live else None)
        odds_by_fixture = self._parse_odds(odds_payload.get("response", []))
        result = []
        for item in fixtures:
            fixture = item.get("fixture", {}); teams = item.get("teams", {}); goals = item.get("goals", {})
            external_id = str(fixture.get("id", ""))
            result.append(ProviderMatch(
                self.name, external_id, _utc(fixture.get("date")), item.get("league", {}).get("name", ""),
                teams.get("home", {}).get("name", ""), teams.get("away", {}).get("name", ""),
                fixture.get("status", {}).get("short", ""), goals.get("home"), goals.get("away"),
                _utc(fixture.get("update")) if fixture.get("update") else None,
                odds_by_fixture.get(external_id, []), item,
            ))
        return result

    @staticmethod
    def _parse_odds(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        parsed: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            fixture_id = str(item.get("fixture", {}).get("id", "")); output = parsed.setdefault(fixture_id, [])
            updated = item.get("update")
            bookmakers = item.get("bookmakers") or ([item.get("bookmaker", {})] if item.get("bookmaker") else [])
            for bookmaker in bookmakers:
                for bet in bookmaker.get("bets", []):
                    market = str(bet.get("name", ""))
                    if market.casefold() not in {"match winner", "home/away", "asian handicap", "goals over/under", "over/under"}:
                        continue
                    for value in bet.get("values", []):
                        output.append({"bookmaker": bookmaker.get("name", ""), "market": market,
                                       "selection": value.get("value"), "odds": value.get("odd"),
                                       "handicap": value.get("handicap"), "provider_updated_at": updated})
        return parsed


class FootballDataProvider(Provider):
    name = "football-data.org"
    base_url = "https://api.football-data.org/v4"
    auth_header = "X-Auth-Token"

    def test_connection(self) -> None:
        self.request("/matches", {"dateFrom": datetime.now(timezone.utc).date().isoformat(), "dateTo": datetime.now(timezone.utc).date().isoformat()})

    def matches(self, day: date, live: bool = False) -> list[ProviderMatch]:
        return self.matches_range(day, day)

    def matches_range(self, start: date, end: date) -> list[ProviderMatch]:
        if end < start:
            raise ValueError("结束日期不能早于开始日期。")
        payload = self.request("/matches", {"dateFrom": start.isoformat(), "dateTo": end.isoformat()})
        result = []
        for item in payload.get("matches", []):
            score = item.get("score", {}).get("fullTime", {})
            result.append(ProviderMatch(
                self.name, str(item.get("id", "")), _utc(item.get("utcDate")),
                item.get("competition", {}).get("name", ""), item.get("homeTeam", {}).get("name", ""),
                item.get("awayTeam", {}).get("name", ""), item.get("status", ""), score.get("home"), score.get("away"),
                _utc(item.get("lastUpdated")) if item.get("lastUpdated") else None, [], item,
            ))
        return result
