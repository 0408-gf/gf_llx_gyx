"""不依赖 GUI 的端到端交付冒烟测试。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from core.betting import Selection, expected_value, generate_combinations, kelly_fraction
from core.odds import market_analysis
from core.prediction import predict
from models.match import Match
from services.database import Database


def run() -> None:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "smoke.db"
        now = datetime.now().replace(microsecond=0)
        matches = [
            Match(now + timedelta(hours=i), "TEST/DEMO联赛", f"TEST主队{i}", f"DEMO客队{i}",
                  2.0 + i * 0.05, 3.2, 3.6 - i * 0.05, source="TEST/DEMO smoke", updated_at=now)
            for i in range(4)
        ]
        db = Database(path)
        assert db.add_matches(matches) == 4
        rows = db.list_matches()
        assert len(rows) == 4 and all(row["source"] == "TEST/DEMO smoke" for row in rows)

        selections: list[Selection] = []
        for row in rows:
            market = market_analysis(row["home_odds"], row["draw_odds"], row["away_odds"])
            assert abs(sum(market["normalized"]) - 1) < 1e-12
            prediction = predict(market["normalized"])
            ev = expected_value(prediction.home, row["home_odds"])
            stake = kelly_fraction(prediction.home, row["home_odds"], fraction=0.25, max_ratio=0.03)
            assert -1 <= ev and 0 <= stake <= 0.03
            db.save_prediction(row["id"], prediction)
            selections.append(Selection(row["id"], "主胜", prediction.home, row["home_odds"], ev, prediction.confidence))

        assert len(generate_combinations(selections, 2)) == 6
        assert len(generate_combinations(selections, 3)) == 4
        assert len(generate_combinations(selections, 4)) == 1
        assert len(db.list_predictions()) == 4
        db.close()

        reopened = Database(path)
        assert len(reopened.list_matches()) == 4
        assert len(reopened.list_predictions()) == 4
        reopened.close()
    print("核心 smoke PASS：4 场 TEST/DEMO 数据、预测、EV、Kelly、串关及 SQLite 重读均成功")


def main() -> int:
    try:
        run()
    except Exception as exc:
        print(f"核心 smoke FAIL：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
