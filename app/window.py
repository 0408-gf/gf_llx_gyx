from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QListWidget, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from core.betting import expected_value, kelly_fraction
from core.odds import market_analysis
from core.prediction import predict
from app.ui_text import CORE_UI_TEXT, NAVIGATION_ITEMS, WINDOW_TITLE
from services.database import Database
from services.importer import import_matches


PAGES = list(NAVIGATION_ITEMS)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__(); self.setWindowTitle(WINDOW_TITLE); self.resize(1180, 720)
        self.db = Database(); self.rows = []
        root = QWidget(); layout = QHBoxLayout(root); self.nav = QListWidget(); self.nav.addItems(PAGES); self.nav.setFixedWidth(180)
        self.pages = QStackedWidget(); layout.addWidget(self.nav); layout.addWidget(self.pages, 1); self.setCentralWidget(root)
        self._build_pages(); self.nav.currentRowChanged.connect(self.pages.setCurrentIndex); self.nav.setCurrentRow(0); self.refresh()

    def _placeholder(self, title: str, text: str = "该区域已建立扩展入口；无数据时不会生成或猜测内容。") -> QWidget:
        page = QWidget(); box = QVBoxLayout(page); label = QLabel(f"<h2>{title}</h2><p>{text}</p>"); label.setWordWrap(True); box.addWidget(label); box.addStretch(); return page

    def _build_pages(self) -> None:
        self.pages.addWidget(self._placeholder("首页/仪表盘", "仅分析用户导入的数据。请先导入 CSV、TXT 或 XLSX。演示文件会明确标注，不代表真实比赛信息。"))
        page = QWidget(); box = QVBoxLayout(page); btn = QPushButton(CORE_UI_TEXT["import_button"]); btn.clicked.connect(self.load_file); box.addWidget(QLabel("<h2>比赛数据导入</h2>支持 CSV、TXT、Excel (.xlsx)，必填：时间、联赛、主队、客队、来源。")); box.addWidget(btn); box.addStretch(); self.pages.addWidget(page)
        page = QWidget(); box = QVBoxLayout(page); self.table = QTableWidget(0, 8); self.table.setHorizontalHeaderLabels(["ID", "时间", "联赛", "主队", "客队", "主胜", "平", "客胜"]); self.table.doubleClicked.connect(lambda: self.nav.setCurrentRow(3)); box.addWidget(QLabel("<h2>比赛列表</h2>双击比赛进入单场分析")); box.addWidget(self.table); self.pages.addWidget(page)
        self.analysis = QTextBrowser(); page = QWidget(); box = QVBoxLayout(page); run = QPushButton(CORE_UI_TEXT["analyze_button"]); run.clicked.connect(self.analyze); box.addWidget(QLabel("<h2>单场分析</h2>透明基础模型，不使用虚构的 AI、状态或伤停数据。")); box.addWidget(run); box.addWidget(self.analysis); self.pages.addWidget(page)
        self.pages.addWidget(self._placeholder("概率预测", "预测结果在单场分析中生成，三项概率总和为 100%。"))
        self.pages.addWidget(self._placeholder("欧赔分析", "显示原始隐含概率、去水概率、返还率和市场 margin。"))
        self.pages.addWidget(self._placeholder("亚盘分析", "展示已导入盘口；第一阶段不对缺失盘口进行推断。"))
        self.pages.addWidget(self._placeholder("EV 分析", "EV = 模型概率 × 当前赔率 − 1；正 EV 不代表必胜。"))
        self.pages.addWidget(self._placeholder("投注组合", "支持单关及 2/3/4 串 1 候选框架，所有输出均为模型建议，不承诺盈利。"))
        self.pages.addWidget(self._bankroll_page())
        self.pages.addWidget(self._placeholder("历史记录", "分析结果会保存至 SQLite，以便后续统计与回测。"))
        self.pages.addWidget(self._placeholder("系统设置", "推荐权重、评级阈值与保守资金参数位于 config.json。"))

    def _bankroll_page(self) -> QWidget:
        page = QWidget(); form = QFormLayout(page); self.capital = QDoubleSpinBox(); self.capital.setRange(0, 1e9); self.capital.setValue(10000)
        self.p = QDoubleSpinBox(); self.p.setRange(0, 1); self.p.setSingleStep(.01); self.p.setValue(.5)
        self.o = QDoubleSpinBox(); self.o.setRange(1.01, 1000); self.o.setValue(2); self.stake = QLabel("—")
        btn = QPushButton("按 1/4 Kelly 计算（单场上限 3%）"); btn.clicked.connect(lambda: self.stake.setText(f"建议比例 {kelly_fraction(self.p.value(), self.o.value(), .25, .03):.2%}，金额 ¥{self.capital.value()*kelly_fraction(self.p.value(), self.o.value(), .25, .03):.2f}"))
        form.addRow(QLabel("<h2>资金管理</h2>默认采用保守的 1/4 Kelly。")); form.addRow("总资金", self.capital); form.addRow("模型概率", self.p); form.addRow("赔率", self.o); form.addRow(btn); form.addRow("结果", self.stake); return page

    def load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入比赛", "", "比赛数据 (*.csv *.txt *.xlsx)")
        if not path: return
        try:
            matches = import_matches(path); self.db.add_matches(matches); self.refresh(); QMessageBox.information(self, CORE_UI_TEXT["import_success"], f"已导入 {len(matches)} 场比赛，数据来源已保留。")
        except Exception as exc:
            QMessageBox.critical(self, CORE_UI_TEXT["import_failure"], str(exc))

    def refresh(self) -> None:
        self.rows = self.db.list_matches(); self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            values = [row[k] for k in ("id", "match_time", "league", "home_team", "away_team", "home_odds", "draw_odds", "away_odds")]
            for c, value in enumerate(values): self.table.setItem(r, c, QTableWidgetItem("暂无数据" if value is None else str(value)))

    def analyze(self) -> None:
        row_index = self.table.currentRow()
        if row_index < 0: QMessageBox.warning(self, CORE_UI_TEXT["select_match"], "请先在比赛列表中选择一场比赛。"); return
        row = self.rows[row_index]
        if any(row[k] is None for k in ("home_odds", "draw_odds", "away_odds")):
            self.analysis.setText("该比赛 1X2 赔率不完整，暂无数据，无法计算。") ; return
        try:
            market = market_analysis(row["home_odds"], row["draw_odds"], row["away_odds"]); prediction = predict(market["normalized"]); self.db.save_prediction(row["id"], prediction)
            labels = ("主胜", "平局", "客胜"); odds = (row["home_odds"], row["draw_odds"], row["away_odds"]); probs = (prediction.home, prediction.draw, prediction.away)
            ev_lines = "<br>".join(f"{x}: 模型 {p:.2%} / 市场隐含 {1/o:.2%} / 赔率 {o:.2f} / EV {expected_value(p,o):+.2%} ({'正期望' if expected_value(p,o)>0 else '非正期望'})" for x,p,o in zip(labels, probs, odds))
            raw = market["raw"]; norm = market["normalized"]
            self.analysis.setHtml(f"<h3>{row['home_team']} vs {row['away_team']}</h3>来源：{row['source']}<br>原始隐含概率：{raw[0]:.2%} / {raw[1]:.2%} / {raw[2]:.2%}<br>去水概率：{norm[0]:.2%} / {norm[1]:.2%} / {norm[2]:.2%}<br>返还率：{market['return_rate']:.2%}，市场 margin：{market['margin']:.2%}<hr>预测：{prediction.home:.2%} / {prediction.draw:.2%} / {prediction.away:.2%}<br>最可能结果：{prediction.result}，置信度：{prediction.confidence:.2%}<hr>{ev_lines}<p><b>提示：正 EV 不等于必胜或稳赢。</b></p>")
        except ValueError as exc: self.analysis.setText(str(exc))
