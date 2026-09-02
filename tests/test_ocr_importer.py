from pathlib import Path

import pytest

from services.ocr_importer import (OCRPreviewRow, OCRToken, ScreenshotOCRError,
                                   cluster_token_rows, is_screenshot,
                                   preview_rows_to_matches, recognize_screenshot,
                                   tokens_to_preview)
from services.importer import import_matches


def _token(text: str, x: float, y: float, confidence: float = 0.96) -> OCRToken:
    return OCRToken(text, ((x, y), (x + 80, y), (x + 80, y + 20), (x, y + 20)), confidence)


def _table_tokens(include_source: bool = True) -> list[OCRToken]:
    headers = [("时间", 0), ("联赛", 220), ("主队", 420), ("客队", 620), ("主胜赔率", 820)]
    if include_source:
        headers.append(("来源", 1020))
    values = [("2026-01-01 19:30", 0), ("测试联赛", 220), ("甲队", 420), ("乙队", 620), ("2.10", 820)]
    if include_source:
        values.append(("本地截图", 1020))
    return [_token(text, x, 0) for text, x in headers] + [_token(text, x, 60) for text, x in values]


@pytest.mark.parametrize("name", ["a.jpg", "a.JPEG", "a.png"])
def test_image_extension_route(name: str):
    assert is_screenshot(name)
    assert not is_screenshot("a.webp")


def test_generic_import_route_requires_preview(tmp_path: Path):
    path = tmp_path / "shot.jpg"; path.write_bytes(b"not-used")
    with pytest.raises(ValueError, match="截图识别预览/校对"):
        import_matches(path)


def test_cluster_tokens_by_geometry():
    rows = cluster_token_rows([_token("B", 200, 61), _token("A", 0, 0), _token("C", 0, 60)])
    assert [[token.text for token in row] for row in rows] == [["A"], ["C", "B"]]


def test_field_mapping_and_source_fallback():
    row = tokens_to_preview(_table_tokens(include_source=False), "shot.png")[0]
    assert row.values["match_time"] == "2026-01-01 19:30"
    assert row.values["home_odds"] == "2.10"
    assert row.values["source"] == "截图OCR:shot.png"
    assert preview_rows_to_matches([row])[0].home_odds == 2.1


def test_low_confidence_is_retained_for_preview():
    tokens = _table_tokens()
    tokens[-2] = _token("2.10", 820, 60, 0.42)
    row = tokens_to_preview(tokens, "shot.jpg")[0]
    assert row.confidences["home_odds"] == 0.42
    assert row.confidence == 0.42


def test_missing_required_blocks_conversion():
    row = OCRPreviewRow({"match_time": "2026-01-01", "league": "", "home_team": "甲", "away_team": "乙", "source": "截图"})
    with pytest.raises(ScreenshotOCRError, match="必须校对完整"):
        preview_rows_to_matches([row])


def test_ocr_date_and_decimal_cleanup():
    row = OCRPreviewRow({"match_time": "2026-01-01 19：30", "league": "测试", "home_team": "甲",
                         "away_team": "乙", "source": "截图", "home_odds": "2，10"})
    match = preview_rows_to_matches([row])[0]
    assert match.match_time.minute == 30
    assert match.home_odds == 2.1


def test_mock_ocr_engine_route(monkeypatch, tmp_path: Path):
    path = tmp_path / "shot.png"; path.write_bytes(b"mock")
    monkeypatch.setattr("services.ocr_importer._prepare_image", lambda unused: object())
    raw = [[[list(point) for point in token.box], token.text, token.confidence] for token in _table_tokens()]
    rows = recognize_screenshot(path, engine=lambda image: (raw, [0.01, 0.01, 0.01]))
    assert rows[0].values["away_team"] == "乙队"


def test_unclear_or_unstructured_ocr_is_rejected():
    with pytest.raises(ScreenshotOCRError, match="比赛表头"):
        tokens_to_preview([_token("随便的文字", 0, 0)], "bad.jpg")
