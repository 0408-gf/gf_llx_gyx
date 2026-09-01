"""无需导入 PySide6 的中文 EXE 界面契约测试。"""
from app.ui_text import CORE_UI_TEXT, NAVIGATION_ITEMS, WINDOW_TITLE


def test_core_chinese_ui_copy_is_packaged() -> None:
    assert WINDOW_TITLE == "足球竞彩分析助手 MVP"
    assert NAVIGATION_ITEMS == (
        "首页/仪表盘", "比赛数据导入", "比赛列表", "单场分析", "概率预测", "欧赔分析",
        "亚盘分析", "EV 分析", "投注组合", "资金管理", "历史记录", "系统设置",
    )
    required = {
        "选择并导入本地文件", "分析选中比赛", "导入成功", "导入失败", "请选择比赛",
        "资金管理", "投注组合", "历史记录", "系统设置",
    }
    assert required <= set(CORE_UI_TEXT.values())
