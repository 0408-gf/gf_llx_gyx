from pathlib import Path

import pytest

from services.importer import import_matches


ROW = "2026-01-01 19:30,测试联赛,甲队,乙队,本地文件\n"


def test_time_source_aliases_and_normalized_headers(tmp_path: Path):
    path = tmp_path / "bom.csv"
    path.write_text("\ufeff  MATCH_TIME , League , HOME_TEAM , away_TEAM , SOURCE  \n" + ROW, encoding="utf-8")
    match = import_matches(path)[0]
    assert (match.league, match.source) == ("测试联赛", "本地文件")

    path.write_text("时间,联赛,主队,客队,来源\n" + ROW, encoding="utf-8")
    assert len(import_matches(path)) == 1


@pytest.mark.parametrize("delimiter", [";", "|"])
def test_txt_delimiters(tmp_path: Path, delimiter: str):
    path = tmp_path / "data.txt"
    path.write_text(delimiter.join(["时间", "联赛", "主队", "客队", "来源"]) + "\n" + delimiter.join(["2026-01-01", "测试", "甲", "乙", "文件"]), encoding="utf-8")
    assert import_matches(path)[0].home_team == "甲"


def test_natural_language_txt_has_helpful_error(tmp_path: Path):
    path = tmp_path / "note.txt"
    path.write_text("今晚甲队和乙队比赛，帮我分析一下。", encoding="utf-8")
    with pytest.raises(ValueError, match="不能导入自然语言") as error:
        import_matches(path)
    assert "时间、联赛、主队、客队、来源" in str(error.value)
    assert "2026-01-01" in str(error.value)


def test_fake_xlsx_has_chinese_recovery_advice(tmp_path: Path):
    path = tmp_path / "fake.xlsx"
    path.write_text("<table></table>", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        import_matches(path)
    message = str(error.value)
    assert "仅改后缀不等于转换" in message
    assert "HTML/TXT/CSV" in message


def test_normal_xlsx(tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "good.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.append([" 时间 ", "联赛", "主队", "客队", "来源"])
    workbook.active.append(["2026-01-01", "测试", "甲", "乙", "Excel"])
    workbook.save(path)
    assert import_matches(path)[0].source == "Excel"


def _html(headers: list[str], values: list[str]) -> str:
    return "<table><tr>" + "".join(f"<th>{x}</th>" for x in headers) + "</tr><tr>" + "".join(f"<td>{x}</td>" for x in values) + "</tr></table>"


def test_chinese_and_english_html(tmp_path: Path):
    chinese = tmp_path / "cn.html"
    chinese.write_text(_html(["时间", "联赛", "主队", "客队", "来源"], ["2026-01-01", "中超", "甲", "乙", "HTML"]), encoding="utf-8")
    assert import_matches(chinese)[0].league == "中超"
    english = tmp_path / "en.html"
    english.write_text(_html(["MATCH_TIME", "LEAGUE", "HOME_TEAM", "AWAY_TEAM", "SOURCE"], ["2026-01-01", "EPL", "A", "B", "local"]), encoding="utf-8")
    assert import_matches(english)[0].away_team == "B"


def test_html_selects_table_with_most_fields(tmp_path: Path):
    path = tmp_path / "tables.html"
    basic = _html(["时间", "联赛", "主队", "客队", "来源"], ["2026-01-01", "错误", "甲", "乙", "HTML"])
    rich = _html(["时间", "联赛", "主队", "客队", "来源", "主胜赔率"], ["2026-01-02", "正确", "丙", "丁", "HTML", "2.1"])
    path.write_text(basic + rich, encoding="utf-8")
    match = import_matches(path)[0]
    assert (match.league, match.home_odds) == ("正确", 2.1)


def test_htm_gb18030(tmp_path: Path):
    path = tmp_path / "data.htm"
    path.write_bytes(_html(["时间", "联赛", "主队", "客队", "来源"], ["2026-01-01", "中文联赛", "甲", "乙", "本地"]).encode("gb18030"))
    assert import_matches(path)[0].league == "中文联赛"


def test_html_entities_nested_tags_and_br(tmp_path: Path):
    path = tmp_path / "nested.html"
    path.write_text("<table><tr><th>时间</th><th>联赛</th><th>主队</th><th>客队</th><th>来源</th></tr>"
                    "<tr><td><b>2026-01-01</b></td><td>甲&amp;乙</td><td><span>红</span><br>队</td><td>蓝队</td><td>本地</td></tr></table>", encoding="utf-8")
    match = import_matches(path)[0]
    assert match.league == "甲&乙"
    assert match.home_team == "红 队"


@pytest.mark.parametrize("content, expected", [
    ("<html>没有表格</html>", "没有真实的 <table>"),
    ("<script>document.write('<table>')</script>", "没有真实的 <table>"),
    ("<table><tr><th>姓名</th></tr><tr><td>甲</td></tr></table>", "没有必填字段齐全"),
])
def test_html_without_usable_table(tmp_path: Path, content: str, expected: str):
    path = tmp_path / "bad.html"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=expected):
        import_matches(path)


def test_html_rejects_merged_cells(tmp_path: Path):
    path = tmp_path / "merged.html"
    path.write_text("<table><tr><th colspan='2'>时间</th><th>联赛</th><th>主队</th><th>客队</th><th>来源</th></tr></table>", encoding="utf-8")
    with pytest.raises(ValueError, match="rowspan/colspan"):
        import_matches(path)


@pytest.mark.parametrize("content, expected", [
    ("", "为空"),
    ("时间,联赛,主队,客队,来源\n", "只有表头"),
    ("时间,,主队,客队,来源\n2026-01-01,x,甲,乙,z", "空字段名"),
    ("时间,时间,联赛,主队,客队,来源\n", "重复字段"),
    ("时间,比赛时间,联赛,主队,客队,来源\n", "含义重复"),
    ("时间,联赛,主队,客队,来源\n2026-01-01,测试,甲,乙\n", "列数与表头不一致"),
])
def test_invalid_delimited_structures(tmp_path: Path, content: str, expected: str):
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=expected):
        import_matches(path)


def test_blank_rows_are_filtered(tmp_path: Path):
    path = tmp_path / "blank.csv"
    path.write_text("时间,联赛,主队,客队,来源\n,,,,\n" + ROW, encoding="utf-8")
    assert len(import_matches(path)) == 1
