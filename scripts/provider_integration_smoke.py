"""可选手工 smoke；没有个人环境变量时安全跳过，CI 永不需要真实密钥。"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from services.providers import APIFootballProvider, FootballDataProvider


def main() -> int:
    primary = os.environ.get("FOOTBALL_API_KEY")
    secondary = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not primary or not secondary:
        print("双源联网 smoke SKIP：未提供个人测试密钥")
        return 0
    day = datetime.now(timezone.utc).date()
    first = APIFootballProvider(primary).matches(day)
    second = FootballDataProvider(secondary).matches(day)
    print(f"双源联网 smoke PASS：API-Football {len(first)} 场，football-data.org {len(second)} 场（未输出密钥）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
