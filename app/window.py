from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from math import ceil
from time import sleep

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMainWindow, QMessageBox, QProgressDialog, QPushButton,
                               QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)

from core.betting import expected_value, kelly_fraction
from core.odds import market_analysis
from core.prediction import predict
from app.ui_text import CORE_UI_TEXT, NAVIGATION_ITEMS, WINDOW_TITLE
from services.database import Database
from services.importer import import_matches
from services.ocr_importer import (OCRPreviewRow, is_screenshot, preview_rows_to_matches,
                                   recognize_screenshot)
from services.credentials import CredentialStore
from services.live_sync import LiveSyncService
from services.providers import APIFootballProvider, FootballDataProvider, ProviderError, RateLimitError
from models.match import Match
from models.provider import VerifiedMatch


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


class SyncPreviewDialog(QDialog):
    def __init__(self, rows: list[VerifiedMatch], parent: QWidget | None = None) -> None:
        super().__init__(parent); self.rows = rows; self.setWindowTitle("同步预览/冲突处理"); self.resize(1050, 460)
        layout = QVBoxLayout(self); layout.addWidget(QLabel("同步结果已先写入独立快照缓存。请选择要新建为本地比赛的项目；冲突项默认不选，请人工核对后再处理。"))
        self.table = QTableWidget(len(rows), 7); self.table.setHorizontalHeaderLabels(["导入", "比赛", "UTC 时间", "状态/比分", "核验", "差异", "赔率来源"])
        for index, verified in enumerate(rows):
            item = verified.primary or verified.secondary
            check = QTableWidgetItem(); check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked if "冲突" in verified.verification else Qt.CheckState.Checked)
            self.table.setItem(index, 0, check)
            odds_source = ""
            if verified.primary and verified.primary.odds:
                odds_source = "、".join(sorted({str(odd.get("bookmaker", "")) for odd in verified.primary.odds if odd.get("bookmaker")}))
            values = [f"{item.home_team} vs {item.away_team}", item.kickoff_utc.isoformat(), f"{item.status} {item.home_score if item.home_score is not None else '-'}:{item.away_score if item.away_score is not None else '-'}", verified.verification, verified.details, odds_source]
            for column, value in enumerate(values, 1):
                cell = QTableWidgetItem(str(value)); cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if "冲突" in verified.verification: cell.setBackground(QColor("#ffb3b3"))
                elif verified.stale or verified.verification == "过期": cell.setBackground(QColor("#fff2a8"))
                self.table.setItem(index, column, cell)
        layout.addWidget(self.table); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认新建所选比赛"); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def selected(self) -> list[VerifiedMatch]:
        return [row for index, row in enumerate(self.rows) if self.table.item(index, 0).checkState() == Qt.CheckState.Checked]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__(); self.setWindowTitle(WINDOW_TITLE); self.resize(1180, 720)
        self.db = Database(); self.rows = []
        self.credentials = CredentialStore(); self.live_service = LiveSyncService(self.db, self.credentials)
        self.auto_timer = QTimer(self); self.auto_timer.timeout.connect(self._auto_refresh); self.auto_ticks = 0
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
        self.pages.addWidget(self._live_page())
        self.pages.addWidget(self._settings_page())

    def _live_page(self) -> QWidget:
        page = QWidget(); box = QVBoxLayout(page)
        self.network_status = QLabel("<b>联网状态：未联网（默认）</b>　上次成功：无　缓存：无")
        controls = QHBoxLayout(); sync = QPushButton("同步今日比赛"); sync.clicked.connect(lambda: self.sync_live(False))
        live = QPushButton("刷新实时结果"); live.clicked.connect(lambda: self.sync_live(True))
        stop = QPushButton("立即停止自动刷新"); stop.clicked.connect(self.stop_auto_refresh)
        controls.addWidget(sync); controls.addWidget(live); controls.addWidget(stop)
        self.live_table = QTableWidget(0, 11)
        self.live_table.setHorizontalHeaderLabels(["比赛", "UTC 时间", "本地时间", "状态/比分", "主源赔率/庄家", "主源更新时间", "复核源更新时间", "核验状态", "差异详情", "主源 ID", "复核源 ID"])
        box.addWidget(QLabel("<h2>实时数据/数据核验</h2>赔率仅来自 API-Football 所返回的第三方 bookmaker，不是官方竞彩足球赔率；football-data.org 只复核赛程、状态与比分。"))
        box.addWidget(self.network_status); box.addLayout(controls); box.addWidget(self.live_table)
        cached = self.live_service.cached_verified()
        if cached:
            self._show_verified(cached, f"离线缓存，数据截至 {self.live_service.cache_time()}")
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget(); form = QFormLayout(page)
        guide = QLabel("<h2>系统设置</h2>联网默认关闭。请自行在 API-Football 与 football-data.org 官方网站注册两个 API Key；软件不包含共享密钥。密钥优先保存到 Windows Credential Manager，绝不写入 config.json 或数据库。")
        guide.setWordWrap(True); form.addRow(guide)
        self.primary_key = QLineEdit(); self.primary_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.secondary_key = QLineEdit(); self.secondary_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API-Football Key", self.primary_key); form.addRow("football-data.org Key", self.secondary_key)
        key_buttons = QHBoxLayout(); save = QPushButton("保存凭据"); save.clicked.connect(self.save_keys)
        delete = QPushButton("删除凭据"); delete.clicked.connect(self.delete_keys)
        test = QPushButton("测试连接"); test.clicked.connect(self.test_connections)
        key_buttons.addWidget(save); key_buttons.addWidget(delete); key_buttons.addWidget(test); form.addRow(key_buttons)
        self.auto_refresh = QCheckBox("主动开启自动刷新（本次运行有效）"); self.auto_refresh.toggled.connect(self.toggle_auto_refresh)
        self.refresh_seconds = QSpinBox(); self.refresh_seconds.setRange(60, 600); self.refresh_seconds.setValue(120); self.refresh_seconds.setSuffix(" 秒")
        form.addRow(self.auto_refresh); form.addRow("主源实时刷新间隔", self.refresh_seconds)
        form.addRow(QLabel("复核源固定约每 5 分钟刷新一次，不与主源同频请求。额度和费用由服务商决定，可能随时变化。"))
        return page

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

    def _background(self, text: str, function):
        progress = QProgressDialog(text, "", 0, 0, self); progress.setCancelButton(None); progress.setMinimumDuration(0); progress.show()
        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="network-sync") as executor:
                future = executor.submit(function)
                while not future.done(): QApplication.processEvents(); sleep(0.02)
                return future.result()
        finally:
            progress.close()

    def sync_live(self, live: bool, automatic: bool = False, include_secondary: bool = True) -> None:
        self.network_status.setText("<b>联网状态：正在通过 HTTPS 请求正式 API……</b>")
        try:
            verified, warning = self._background("正在后台同步双数据源……", lambda: self.live_service.sync(datetime.now().astimezone().date(), live, include_secondary, "自动" if automatic else "手动"))
            self._show_verified(verified, warning or "联网成功")
            if warning:
                QMessageBox.warning(self, "已显示缓存", warning)
                return
            if not automatic:
                preview = SyncPreviewDialog(verified, self)
                if preview.exec() == QDialog.DialogCode.Accepted:
                    self._import_verified(preview.selected())
        except RateLimitError as exc:
            self.stop_auto_refresh(); cached = self.live_service.cached_verified()
            if cached: self._show_verified(cached, f"额度耗尽，自动刷新已暂停；显示缓存截至 {self.live_service.cache_time()}")
            self.network_status.setText(self.network_status.text() + f"　{exc}")
        except ProviderError as exc:
            self.network_status.setText(f"<b>联网状态：请求失败</b>　{exc}　缓存截至 {self.live_service.cache_time() or '无'}")
            QMessageBox.warning(self, "同步失败", str(exc))

    def _show_verified(self, rows: list[VerifiedMatch], status: str) -> None:
        self.live_table.setRowCount(len(rows))
        for row_index, verified in enumerate(rows):
            item = verified.primary or verified.secondary; primary = verified.primary; secondary = verified.secondary
            score = f"{item.status} {item.home_score if item.home_score is not None else '-'}:{item.away_score if item.away_score is not None else '-'}"
            odds = ""
            if primary and primary.odds:
                odds = "；".join(f"{odd.get('market')} {odd.get('selection')} {odd.get('odds')} ({odd.get('bookmaker')})" for odd in primary.odds[:6])
            values = [f"{item.league}｜{item.home_team} vs {item.away_team}", item.kickoff_utc.isoformat(), item.kickoff_utc.astimezone().strftime("%Y-%m-%d %H:%M %Z"), score, odds,
                      primary.provider_updated_at.isoformat() if primary and primary.provider_updated_at else "", secondary.provider_updated_at.isoformat() if secondary and secondary.provider_updated_at else "",
                      verified.verification, verified.details, primary.external_id if primary else "", secondary.external_id if secondary else ""]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if "冲突" in verified.verification: cell.setBackground(QColor("#ffb3b3"))
                elif verified.stale or verified.verification == "过期": cell.setBackground(QColor("#fff2a8"))
                self.live_table.setItem(row_index, column, cell)
        cache_time = self.live_service.cache_time() or "无"
        quota = "；".join(f"{provider}: " + ", ".join(f"{key}={value}" for key, value in values.items()) for provider, values in self.live_service.last_quota.items() if values)
        self.network_status.setText(f"<b>联网状态：{status}</b>　上次成功/缓存：{cache_time}　缓存新鲜度：{'可能过期' if any(row.stale for row in rows) else '最新快照'}　{quota}")

    def _import_verified(self, rows: list[VerifiedMatch]) -> None:
        matches = []
        for verified in rows:
            item = verified.primary or verified.secondary
            odds = {"home": None, "draw": None, "away": None}; bookmaker = ""
            if verified.primary:
                for odd in verified.primary.odds:
                    if str(odd.get("market", "")).casefold() != "match winner": continue
                    selection = str(odd.get("selection", "")).casefold()
                    key = "home" if selection in {"home", "1"} else "draw" if selection in {"draw", "x"} else "away" if selection in {"away", "2"} else None
                    if key and odds[key] is None:
                        try: odds[key] = float(odd.get("odds"))
                        except (TypeError, ValueError): pass
                        bookmaker = str(odd.get("bookmaker", ""))
            source = f"{item.provider} 快照" + (f" / bookmaker: {bookmaker}" if bookmaker else "")
            matches.append(Match(item.kickoff_utc.replace(tzinfo=None), item.league, item.home_team, item.away_team,
                                 odds["home"], odds["draw"], odds["away"], source=source, updated_at=datetime.now()))
        if matches:
            self.db.add_matches(matches)
            for match, verified in zip(matches, rows):
                if verified.primary:
                    self.db.save_external_mapping(verified.primary.external_id, verified.secondary.external_id if verified.secondary else None, match.id)
            self.refresh(); QMessageBox.information(self, "同步导入完成", f"已新建 {len(matches)} 场本地比赛；原有手工/文件/OCR 数据未被覆盖。")

    def save_keys(self) -> None:
        saved = []
        for provider, field in (("api-football", self.primary_key), ("football-data", self.secondary_key)):
            if field.text().strip(): saved.append(self.credentials.set(provider, field.text()))
            field.clear()
        if not saved: QMessageBox.warning(self, "凭据", "请输入至少一个 API Key。")
        elif all(saved): QMessageBox.information(self, "凭据", "API Key 已保存到系统凭据库。")
        else: QMessageBox.warning(self, "凭据", "系统凭据库不可用；API Key 仅保存在当前进程内存，关闭软件后即丢失，不会明文落盘。")

    def delete_keys(self) -> None:
        self.credentials.delete("api-football"); self.credentials.delete("football-data")
        self.primary_key.clear(); self.secondary_key.clear(); QMessageBox.information(self, "凭据", "两个 API Key 已删除。")

    def test_connections(self) -> None:
        def test():
            first = self.credentials.get("api-football"); second = self.credentials.get("football-data")
            if not first or not second: raise ProviderError("请先保存两个 API Key。")
            APIFootballProvider(first).test_connection(); FootballDataProvider(second).test_connection()
        try:
            self._background("正在测试两个正式 API……", test); QMessageBox.information(self, "测试连接", "两个数据源连接成功。")
        except ProviderError as exc: QMessageBox.warning(self, "测试连接", str(exc))

    def toggle_auto_refresh(self, enabled: bool) -> None:
        if enabled:
            if not self.credentials.get("api-football") or not self.credentials.get("football-data"):
                self.auto_refresh.blockSignals(True); self.auto_refresh.setChecked(False); self.auto_refresh.blockSignals(False)
                QMessageBox.warning(self, "自动刷新", "请先保存两个 API Key。"); return
            self.auto_ticks = 0; self.auto_timer.start(self.refresh_seconds.value() * 1000)
            self.network_status.setText("<b>联网状态：自动刷新已由用户主动开启</b>")
        else: self.stop_auto_refresh()

    def _auto_refresh(self) -> None:
        self.auto_ticks += 1
        # 主源每次刷新；复核源至少间隔约五分钟，避免同频浪费额度。
        secondary_every = max(1, ceil(300 / self.refresh_seconds.value()))
        self.sync_live(True, True, self.auto_ticks % secondary_every == 0)

    def stop_auto_refresh(self) -> None:
        self.auto_timer.stop()
        if hasattr(self, "auto_refresh"):
            self.auto_refresh.blockSignals(True); self.auto_refresh.setChecked(False); self.auto_refresh.blockSignals(False)
        if hasattr(self, "network_status"): self.network_status.setText(f"<b>联网状态：自动刷新已停止</b>　缓存截至 {self.live_service.cache_time() or '无'}")

    def closeEvent(self, event) -> None:
        self.auto_timer.stop(); self.db.close(); event.accept()

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
