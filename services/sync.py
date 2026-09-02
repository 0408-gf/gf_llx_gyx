from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from models.provider import ProviderMatch, VerifiedMatch


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    words = re.findall(r"[\w\u3400-\u9fff]+", value)
    noise = {"fc", "cf", "afc", "football", "club", "足球俱乐部"}
    return "".join(word for word in words if word not in noise)


def _compatible(primary: ProviderMatch, secondary: ProviderMatch, tolerance_seconds: int) -> bool:
    return (abs((primary.kickoff_utc - secondary.kickoff_utc).total_seconds()) <= tolerance_seconds
            and normalize_name(primary.league) == normalize_name(secondary.league)
            and normalize_name(primary.home_team) == normalize_name(secondary.home_team)
            and normalize_name(primary.away_team) == normalize_name(secondary.away_team))


def _differences(primary: ProviderMatch, secondary: ProviderMatch) -> list[str]:
    differences = []
    if abs((primary.kickoff_utc - secondary.kickoff_utc).total_seconds()) > 60:
        differences.append("开赛时间不同")
    if primary.status and secondary.status and primary.status != secondary.status:
        differences.append("状态代码不同")
    if (primary.home_score is not None and secondary.home_score is not None
            and (primary.home_score, primary.away_score) != (secondary.home_score, secondary.away_score)):
        differences.append("比分不同")
    if normalize_name(primary.league) != normalize_name(secondary.league):
        differences.append("联赛名称不同")
    return differences


def verify_sources(primary: Iterable[ProviderMatch], secondary: Iterable[ProviderMatch],
                   stable_mappings: dict[str, str] | None = None, tolerance_seconds: int = 15 * 60,
                   stale_after_seconds: int = 10 * 60, now: datetime | None = None) -> list[VerifiedMatch]:
    primary = list(primary); remaining = {item.external_id: item for item in secondary}
    mappings = stable_mappings or {}; now = now or datetime.now(timezone.utc)
    output: list[VerifiedMatch] = []
    for item in primary:
        mapped_id = mappings.get(item.external_id)
        if mapped_id:
            candidates = [remaining[mapped_id]] if mapped_id in remaining else []
        else:
            candidates = [other for other in remaining.values() if _compatible(item, other, tolerance_seconds)]
        updated = item.provider_updated_at or item.kickoff_utc
        stale = (now - updated).total_seconds() > stale_after_seconds
        if len(candidates) == 1:
            other = candidates[0]; remaining.pop(other.external_id, None)
            differences = _differences(item, other)
            verification = "冲突" if any(value in differences for value in ("比分不同", "开赛时间不同")) else ("部分一致" if differences else "双源一致")
            output.append(VerifiedMatch(item, other, "过期" if stale and verification != "冲突" else verification, "、".join(differences), stale))
        elif len(candidates) > 1:
            output.append(VerifiedMatch(item, None, "冲突/待人工确认", "存在多个复核源候选，未自动合并", stale))
        else:
            output.append(VerifiedMatch(item, None, "过期" if stale else "仅主源", "复核源未找到保守匹配", stale))
    output.extend(VerifiedMatch(None, item, "仅复核源", "复核源不提供赔率") for item in remaining.values())
    return output
