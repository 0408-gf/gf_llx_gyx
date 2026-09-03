from __future__ import annotations


def _validate(odds: tuple[float, ...]) -> None:
    if not odds or any(not isinstance(x, (int, float)) or isinstance(x, bool) or x <= 1 for x in odds):
        raise ValueError("欧赔必须是大于 1 的数字")


def implied_probabilities(home: float, draw: float, away: float) -> tuple[float, float, float]:
    values = (home, draw, away)
    _validate(values)
    return tuple(1 / x for x in values)  # type: ignore[return-value]


def market_analysis(home: float, draw: float, away: float) -> dict[str, object]:
    raw = implied_probabilities(home, draw, away)
    total = sum(raw)
    return {
        "raw": raw,
        "normalized": tuple(x / total for x in raw),
        "margin": total - 1,
        "return_rate": 1 / total,
    }
