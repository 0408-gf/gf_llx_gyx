from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if sys.platform == "win32":
    from PySide6.QtWidgets import QApplication
    from app.window import MainWindow
else:
    try:
        from PySide6.QtWidgets import QApplication
        from app.window import MainWindow
    except (ImportError, OSError) as exc:
        pytest.skip(f"Linux 环境缺少 PySide6 或 Qt 系统库：{exc}", allow_module_level=True)


def test_main_window_has_all_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    expected_navigation = [
        "首页/仪表盘", "比赛数据导入", "比赛列表", "单场分析", "概率预测", "欧赔分析",
        "亚盘分析", "EV 分析", "投注组合", "资金管理", "历史记录", "系统设置",
    ]
    assert window.windowTitle() == "足球竞彩分析助手 MVP"
    assert window.pages.count() == 12
    assert window.nav.count() == 12
    assert [window.nav.item(index).text() for index in range(12)] == expected_navigation
    app.processEvents()
    window.close()
    window.db.close()


def test_cancel_ocr_preview_does_not_write_database(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from services.ocr_importer import OCRPreviewRow

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    monkeypatch.setattr("app.window.QFileDialog.getOpenFileName", lambda *args: (str(tmp_path / "shot.png"), ""))
    monkeypatch.setattr("app.window.recognize_screenshot", lambda path: [OCRPreviewRow({
        "match_time": "2026-01-01", "league": "测试", "home_team": "甲",
        "away_team": "乙", "source": "截图OCR:shot.png",
    })])

    class CancelPreview:
        def __init__(self, rows, parent): pass
        def exec(self): return QDialog.DialogCode.Rejected

    monkeypatch.setattr("app.window.OCRPreviewDialog", CancelPreview)
    calls = []
    monkeypatch.setattr(window.db, "add_matches", lambda matches: calls.append(matches))
    window.load_file()
    assert calls == []
    window.close(); window.db.close()
