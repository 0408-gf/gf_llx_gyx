from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import prod


def expected_value(probability: float, odds: float) -> float:
    if not 0 <= probability <= 1 or odds <= 1:
        raise ValueError("概率须在 0~1 且赔率须大于 1")
    return probability * odds - 1


def kelly_fraction(probability: float, odds: float, fraction: float = 1.0,
                   max_ratio: float = 0.03) -> float:
    if not 0 <= probability <= 1 or odds <= 1 or not 0 <= fraction <= 1 or not 0 <= max_ratio <= 1:
        raise ValueError("Kelly 参数无效")
    b = odds - 1
    full = (b * probability - (1 - probability)) / b
    return min(max_ratio, max(0.0, full * fraction))


@dataclass(frozen=True)
class Selection:
    match_id: int
    label: str
    probability: float
    odds: float
    ev: float
    confidence: float


def generate_combinations(selections: list[Selection], legs: int) -> list[dict[str, object]]:
    if legs not in (1, 2, 3, 4):
        raise ValueError("仅支持单关、2串1、3串1、4串1")
    result = []
    for items in combinations(selections, legs):
        if len({item.match_id for item in items}) != legs:
            continue
        result.append({"selections": items, "odds": prod(x.odds for x in items),
                       "probability": prod(x.probability for x in items), "notice": "模型建议，不承诺盈利"})
    return result


def recommendation_score(probability: float, ev: float, confidence: float, config: dict) -> tuple[float, str]:
    weights = config["recommendation_weights"]
    score = probability * weights["probability"] + max(-1, min(1, ev)) * weights["ev"] + confidence * weights["confidence"]
    limits = config["recommendation_thresholds"]
    return score, "A" if score >= limits["A"] else "B" if score >= limits["B"] else "C"
