from __future__ import annotations

from datetime import datetime

from models.match import Prediction


def predict(base: tuple[float, float, float], home_form: float = 0, away_form: float = 0,
            strength: float = 0, home_advantage: float = 0.05) -> Prediction:
    """透明的线性修正模型；用户评分范围建议为 -1 到 1。"""
    if len(base) != 3 or any(x < 0 for x in base) or sum(base) <= 0:
        raise ValueError("基础概率无效")
    h, d, a = (x / sum(base) for x in base)
    adjustment = max(-0.20, min(0.20, (home_form - away_form) * 0.06 + strength * 0.06 + home_advantage))
    h = max(0.01, h + adjustment)
    a = max(0.01, a - adjustment)
    values = (h, max(0.01, d), a)
    values = tuple(x / sum(values) for x in values)
    labels = ("主胜", "平局", "客胜")
    top = max(range(3), key=lambda i: values[i])
    ordered = sorted(values, reverse=True)
    confidence = max(0.0, min(1.0, ordered[0] - ordered[1] + ordered[0]))
    return Prediction(*values, labels[top], confidence, datetime.now())
