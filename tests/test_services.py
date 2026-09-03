from pathlib import Path

from services.database import Database
from services.importer import import_matches
from services.paths import default_database_path


def test_csv_import_and_database(tmp_path: Path):
    source = tmp_path / "data.csv"
    source.write_text("比赛时间,联赛,主队,客队,主胜赔率,数据来源\n2026-01-01 19:30,测试联赛,甲队,乙队,2.1,用户文件\n", encoding="utf-8")
    matches = import_matches(source)
    assert matches[0].draw_odds is None
    db = Database(tmp_path / "test.db")
    assert db.add_matches(matches) == 1
    assert db.list_matches()[0]["source"] == "用户文件"


def test_xlsx_import(tmp_path: Path):
    openpyxl = __import__("pytest").importorskip("openpyxl")
    Workbook = openpyxl.Workbook
    path = tmp_path / "data.xlsx"; wb = Workbook(); ws = wb.active
    ws.append(["比赛时间", "联赛", "主队", "客队", "数据来源"]); ws.append(["2026-01-01", "测试", "甲", "乙", "测试文件"]); wb.save(path)
    assert len(import_matches(path)) == 1


def test_default_database_path_uses_user_data_directory(tmp_path: Path, monkeypatch):
    import sys
    variable = "LOCALAPPDATA" if sys.platform == "win32" else "XDG_DATA_HOME"
    monkeypatch.setenv(variable, str(tmp_path))
    path = default_database_path()
    assert path == tmp_path / "FootballJCAssistant" / "football.db"
    assert path.parent.is_dir()
    db = Database()
    assert db.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    db.close()
