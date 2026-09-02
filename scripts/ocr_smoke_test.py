"""使用随包模型对程序生成的清晰表格做一次真正的离线 OCR 冒烟测试。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from services.ocr_importer import preview_rows_to_matches, recognize_screenshot


def _font_path() -> str:
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    return str(next((path for path in candidates if path.exists()), candidates[0]))


def run() -> None:
    from PIL import Image, ImageDraw, ImageFont

    headers = ["match_time", "league", "home_team", "away_team", "home_odds"]
    values = ["2026-01-01 19:30", "TEST LEAGUE", "RED TEAM", "BLUE TEAM", "2.10"]
    widths = [390, 330, 330, 330, 250]
    image = Image.new("RGB", (sum(widths) + 1, 241), "white")
    draw = ImageDraw.Draw(image); font = ImageFont.truetype(_font_path(), 30)
    left = 0
    for width, header, value in zip(widths, headers, values):
        draw.rectangle((left, 0, left + width, 120), outline="black", width=3)
        draw.rectangle((left, 120, left + width, 240), outline="black", width=3)
        draw.text((left + 12, 38), header, fill="black", font=font)
        draw.text((left + 12, 158), value, fill="black", font=font)
        left += width
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "ocr-smoke.png"; image.save(path)
        rows = recognize_screenshot(path)
        matches = preview_rows_to_matches(rows)
        assert len(matches) == 1
        assert matches[0].source == "截图OCR:ocr-smoke.png"
        assert matches[0].home_odds == 2.1
    print("离线 OCR smoke PASS：模型已加载，表格截图已完成识别、分列、校验与 Match 转换")


def main() -> int:
    try:
        run()
    except Exception as exc:
        print(f"离线 OCR smoke FAIL：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
