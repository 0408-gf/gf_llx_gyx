"""中文界面文案常量。

此模块不导入 Qt，允许在缺少图形系统库的构建环境中验证交付文案。
"""
from __future__ import annotations


WINDOW_TITLE = "足球竞彩分析助手 MVP"

NAVIGATION_ITEMS = (
    "首页/仪表盘",
    "比赛数据导入",
    "比赛列表",
    "单场分析",
    "概率预测",
    "欧赔分析",
    "亚盘分析",
    "EV 分析",
    "投注组合",
    "资金管理",
    "历史记录",
    "实时数据/数据核验",
    "系统设置",
)

CORE_UI_TEXT = {
    "import_button": "选择并导入本地文件",
    "analyze_button": "分析选中比赛",
    "import_success": "导入成功",
    "import_failure": "导入失败",
    "select_match": "请选择比赛",
    "bankroll": "资金管理",
    "combinations": "投注组合",
    "history": "历史记录",
    "settings": "系统设置",
}
