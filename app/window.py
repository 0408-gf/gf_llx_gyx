from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import sleep

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QListWidget, QMainWindow, QMessageBox, QProgressDialog, QPushButton,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)

from core.betting import expected_value, kelly_fraction
from core.odds import market_analysis
from core.prediction import predict
from app.ui_text import CORE_UI_TEXT, NAVIGATION_ITEMS, WINDOW_TITLE
from services.database import Database
from services.importer import import_matches
from services.ocr_importer import (OCRPreviewRow, is_screenshot, preview_rows_to_matches,
                                   recognize_screenshot)


PAGES = list(NAVIGATION_ITEMS)
OCR_COLUMNS = [
    ("match_time", "时间"), ("league", "联赛"), ("home_team", "主队"),
    ("away_team", "客队"), ("source", "来源"), ("home_odds", "主胜赔率"),
    ("draw_odds", "平局赔率"), ("away_odds", "客胜赔率"),
]


class OCRPreviewDialog(QDialog):
    """OCR 结果必须由用户校对并确认；对话框本身不接触数据库。"""

    def __init__(self, rows: list[OCRPreviewRow], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle("截图识别预览/校对")
        self.resize(1050, 460)
        layout = QVBoxLayout(self)
        note = QLabel("请逐项核对 OCR 结果。红色表示低置信度或必填内容缺失；只有必填字段完整后才能确认导入。")
        note.setWordWrap(True); layout.addWidget(note)
        self.table = QTableWidget(len(rows), len(OCR_COLUMNS) + 1)
        self.table.setHorizontalHeaderLabels([label for _, label in OCR_COLUMNS] + ["最低置信度"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        layout.addWidget(self.table)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认导入")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)
        for row_index, row in enumerate(rows):
            for column_index, (key, _) in enumerate(OCR_COLUMNS):
                item = QTableWidgetItem(row.values.get(key, "")); item.setData(Qt.ItemDataRole.UserRole, row.confidences.get(key, 0.0))
                self.table.setItem(row_index, column_index, item)
            confidence = QTableWidgetItem(f"{row.confidence:.0%}")
            confidence.setFlags(confidence.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, len(OCR_COLUMNS), confidence)
        self.table.cellChanged.connect(self._refresh_validation)
        self._refresh_validation()

    def _refresh_validation(self) -> None:
        self.table.blockSignals(True)
        all_valid = bool(self.rows)
        for row_index, row in enumerate(self.rows):
            for column_index, (key, _) in enumerate(OCR_COLUMNS):
                item = self.table.item(row_index, column_index)
                value = item.text().strip() if item else ""
                original = row.values.get(key, "")
                row.values[key] = value
                if value != original:
                    row.confidences[key] = 1.0  # 用户已主动校正此单元格。
                confidence = row.confidences.get(key, 0.0)
                invalid = (key in {"match_time", "league", "home_team", "away_team", "source"} and not value)
                low = bool(value) and confidence < 0.75
                item.setBackground(QColor("#ffb3b3") if invalid or low else QColor("white"))
                all_valid &= not invalid
            score_item = self.table.item(row_index, len(OCR_COLUMNS))
            score_item.setText(f"{row.confidence:.0%}")
            score_item.setBackground(QColor("#ffb3b3") if row.confidence < 0.75 else QColor("white"))
        self.table.blockSignals(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(all_valid)


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
        self.pages.addWidget(self._placeholder("首页/仪表盘", "仅分析用户导入的数据。请先导入 CSV、TXT、XLSX、HTML 或截图图片。演示文件会明确标注，不代表真实比赛信息。"))
        page = QWidget(); box = QVBoxLayout(page); btn = QPushButton(CORE_UI_TEXT["import_button"]); btn.clicked.connect(self.load_file)
        help_btn = QPushButton("查看导入格式"); help_btn.clicked.connect(self.show_import_format)
        box.addWidget(QLabel("<h2>比赛数据导入</h2>支持 CSV、TXT、Excel (.xlsx)、HTML (.html/.htm)、截图图片 (.jpg/.jpeg/.png)，必填：时间、联赛、主队、客队、来源。<br>HTML 必须包含真实 &lt;table&gt;；截图会先离线 OCR 并要求人工校对，程序不会联网。")); box.addWidget(btn); box.addWidget(help_btn); box.addStretch(); self.pages.addWidget(page)
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
        path, _ = QFileDialog.getOpenFileName(self, "导入比赛", "", "比赛数据 (*.csv *.txt *.xlsx *.html *.htm *.jpg *.jpeg *.png)")
        if not path: return
        try:
            if is_screenshot(path):
                rows = self._recognize_with_progress(path)
                preview = OCRPreviewDialog(rows, self)
                if preview.exec() != QDialog.DialogCode.Accepted:
                    return
                matches = preview_rows_to_matches(rows)
            else:
                matches = import_matches(path)
            self.db.add_matches(matches); self.refresh(); QMessageBox.information(self, CORE_UI_TEXT["import_success"], f"已导入 {len(matches)} 场比赛，数据来源已保留。")
        except Exception as exc:
            QMessageBox.critical(self, CORE_UI_TEXT["import_failure"], str(exc))

    def _recognize_with_progress(self, path: str) -> list[OCRPreviewRow]:
        progress = QProgressDialog("正在后台离线识别截图，请稍候……", "", 0, 0, self)
        progress.setWindowTitle("截图 OCR"); progress.setCancelButton(None); progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0); progress.show()
        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="screenshot-ocr") as executor:
                future = executor.submit(recognize_screenshot, path)
                while not future.done():
                    QApplication.processEvents()
                    sleep(0.02)
                return future.result()
        finally:
            progress.close()

    def show_import_format(self) -> None:
        QMessageBox.information(
            self,
            "导入格式",
            "支持 CSV、TXT、XLSX、HTML/HTM 和截图图片 JPG/JPEG/PNG。必填表头：时间、联赛、主队、客队、来源。\n\n"
            "TXT 可使用制表符、逗号、分号或竖线分隔。HTML 必须在本地源码中包含真实 <table>；"
            "不会执行 JavaScript、加载外部资源、联网或从网页文字猜测比赛。HTML 合并单元格不受支持。\n\n"
            "截图使用随软件打包的离线 OCR，识别后必须在预览表中校对并确认；低清、裁剪或无法分列的截图不会导入。",
        )

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
