from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from models.match import Match

FIELD_ALIASES = {
    "match_time": ("match_time", "比赛时间", "日期时间"), "league": ("league", "联赛"),
    "home_team": ("home_team", "主队"), "away_team": ("away_team", "客队"),
    "home_odds": ("home_odds", "主胜赔率"), "draw_odds": ("draw_odds", "平局赔率"),
    "away_odds": ("away_odds", "客胜赔率"), "asian_line": ("asian_line", "亚洲让球盘口"),
    "asian_home_odds": ("asian_home_odds", "主队亚盘赔率"), "asian_away_odds": ("asian_away_odds", "客队亚盘赔率"),
    "total_line": ("total_line", "大小球盘口"), "over_odds": ("over_odds", "大球赔率"),
    "under_odds": ("under_odds", "小球赔率"), "source": ("source", "数据来源"), "updated_at": ("updated_at", "更新时间")
}
NUMBERS = {"home_odds", "draw_odds", "away_odds", "asian_line", "asian_home_odds", "asian_away_odds", "total_line", "over_odds", "under_odds"}


def _date(value: Any) -> datetime:
    if isinstance(value, datetime): return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d"):
        try: return datetime.strptime(text, fmt)
        except ValueError: pass
    raise ValueError(f"无法识别日期：{text}")


def _mapped(row: dict[str, Any], line: int) -> Match:
    data = {key: next((row.get(alias) for alias in aliases if row.get(alias) not in (None, "")), None) for key, aliases in FIELD_ALIASES.items()}
    missing = [x for x in ("match_time", "league", "home_team", "away_team", "source") if not data[x]]
    if missing: raise ValueError(f"第 {line} 行缺少必填字段：{', '.join(missing)}")
    for key in NUMBERS:
        if data[key] is not None:
            try: data[key] = float(data[key])
            except (TypeError, ValueError): raise ValueError(f"第 {line} 行 {key} 不是数字") from None
    data["match_time"] = _date(data["match_time"])
    data["updated_at"] = _date(data["updated_at"]) if data["updated_at"] else datetime.now()
    return Match(**data)


def import_matches(path: str | Path) -> list[Match]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".csv", ".txt"):
        with path.open(encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096); f.seek(0)
            delimiter = "\t" if suffix == ".txt" and "\t" in sample else ","
            rows = list(csv.DictReader(f, delimiter=delimiter))
    elif suffix == ".xlsx":
        from openpyxl import load_workbook
        ws = load_workbook(path, read_only=True, data_only=True).active
        values = ws.iter_rows(values_only=True); headers = [str(x).strip() if x is not None else "" for x in next(values)]
        rows = [dict(zip(headers, row)) for row in values]
    else:
        raise ValueError("仅支持 CSV、TXT 和 XLSX；PDF/图片/OCR/网络数据将在后续版本支持")
    if not rows: raise ValueError("文件中没有比赛数据")
    return [_mapped(row, i) for i, row in enumerate(rows, 2)]
