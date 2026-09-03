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
        "亚盘分析", "EV 分析", "投注组合", "资金管理", "历史记录", "实时数据/数据核验", "系统设置",
    ]
    assert window.windowTitle() == "足球竞彩分析助手 MVP"
    assert window.pages.count() == 13
    assert window.nav.count() == 13
    assert [window.nav.item(index).text() for index in range(13)] == expected_navigation
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


def test_auto_refresh_is_opt_in_and_can_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path)); app = QApplication.instance() or QApplication([])
    window = MainWindow(); assert not window.auto_timer.isActive()
    monkeypatch.setattr(window.credentials, "get", lambda provider: "mock-key")
    window.toggle_auto_refresh(True); assert window.auto_timer.isActive()
    window.stop_auto_refresh(); assert not window.auto_timer.isActive()
    window.close()


def test_cancel_sync_preview_does_not_write_database(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from models.provider import ProviderMatch, VerifiedMatch
    from PySide6.QtWidgets import QDialog
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path)); app = QApplication.instance() or QApplication([])
    window = MainWindow(); item = ProviderMatch("API-Football", "1", datetime.now(timezone.utc), "联赛", "甲", "乙", "NS")
    monkeypatch.setattr(window, "_background", lambda text, fn: ([VerifiedMatch(item, None, "仅主源")], None))
    class CancelPreview:
        def __init__(self, rows, parent): pass
        def exec(self): return QDialog.DialogCode.Rejected
    monkeypatch.setattr("app.window.SyncPreviewDialog", CancelPreview)
    calls = []; monkeypatch.setattr(window.db, "add_matches", lambda matches: calls.append(matches))
    window.sync_live(False); assert calls == []
    window.close()
