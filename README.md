# 足球竞彩分析助手（MVP）

面向 Windows 10/11 的中文桌面足球比赛预测与中国竞彩足球分析工具。程序只分析用户真实导入的数据；缺失字段显示“暂无数据”，不会编造比赛、赔率、伤停、球队状态或资金流向。预测和组合均为可解释的模型建议，**不代表必胜，也不承诺盈利**。

## 已完成功能

- PySide6 中文桌面框架，包含仪表盘、导入、比赛列表、单场分析、概率预测、欧赔、亚盘、EV、投注组合、资金管理、历史和设置 12 个功能区。
- Windows EXE 的窗口标题“足球竞彩分析助手 MVP”、全部导航、操作按钮、字段名称、提示和错误信息均使用中文；EV（期望值）、Kelly（凯利资金管理）等通用行业缩写会保留，并在界面中配合中文说明。
- CSV、TXT、XLSX、本地 HTML/HTM 和 JPG/JPEG/PNG 表格截图导入；截图使用随发布包提供的离线 RapidOCR/ONNX 模型，并在写入前强制人工预览校对。赔率允许为空。
- 1X2 隐含概率、返还率、overround/margin 及去水概率。
- 欧赔基础概率结合可替换线性修正的透明预测引擎，输出三项概率、最可能结果和置信度。
- `EV = p × odds - 1`、固定比例配置、全 Kelly/1/2 Kelly/1/4 Kelly 和最大单场比例限制。
- 胜平负及让球胜平负的数据基础；单关、2串1、3串1、4串1组合算法。比分、总进球、半全场已列入后续范围。
- 推荐评分权重和 A/B/C 阈值位于 `config.json`，没有硬编码在 UI。
- SQLite 保存导入比赛、原始赔率和带分析时间的预测；数据库表已为组合和资金记录准备。Windows 数据库默认位于 `%LOCALAPPDATA%\FootballJCAssistant\football.db`，不会写在只读的 EXE 目录中。

## 目录

| 路径 | 用途 |
|---|---|
| `app/` | PySide6 启动入口与界面 |
| `core/` | 欧赔、预测、EV、Kelly、组合算法 |
| `models/` | 比赛与预测统一模型 |
| `services/` | 静态文件导入与 SQLite 持久化 |
| `data/` | 数据库运行目录及明确标注的演示文件 |
| `tests/` | 自动测试 |
| `config.json` | 推荐权重、评级阈值、资金参数 |
| `build_windows.bat` / `football_jc.spec` | Windows 打包配置 |

`imports/`、`reports/`、`assets/` 可在产生相应用户文件时创建；当前不放置假接口或空实现。

## 开发运行

需要 Python 3.11 或更高版本：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.main
```

启动后不需要再手工运行 Python 命令：日常使用均通过图形界面完成。进入“比赛数据导入”选择文件，随后在“比赛列表”选择一行，进入“单场分析”计算。

## 导入模板

支持 `.csv`、`.xlsx`、`.txt`、本地 `.html`/`.htm` 和表格截图 `.jpg`/`.jpeg`/`.png`。TXT/CSV 可用制表符、逗号、分号或竖线分隔，首行必须是字段名；自然语言 TXT 不会被猜测成比赛。必填字段为时间、联赛、主队、客队、来源；也兼容“比赛时间/日期时间”和“数据来源”等原有名称，其余赔率均可留空。

```text
比赛时间,联赛,主队,客队,主胜赔率,平局赔率,客胜赔率,亚洲让球盘口,主队亚盘赔率,客队亚盘赔率,大小球盘口,大球赔率,小球赔率,数据来源,更新时间
```

也支持对应英文名：`match_time, league, home_team, away_team, home_odds, draw_odds, away_odds, asian_line, asian_home_odds, asian_away_odds, total_line, over_odds, under_odds, source, updated_at`。日期建议使用 `YYYY-MM-DD HH:MM`。

TXT/CSV 的 UTF-8 BOM、字段名前后空白以及英文字段大小写会自动规范化。空文件、只有表头、空表头、重复或含义重复的表头、数据列数错位都会在导入前后给出中文提示。XLSX 必须是真正的 Excel 工作簿；文件损坏或伪造后缀时，请恢复正确扩展名后按 HTML/TXT/CSV 导入，或在 Excel/WPS 中“另存为 Excel 工作簿 (*.xlsx)”。**仅修改后缀不等于转换文件格式。**

### HTML 示例与安全边界

HTML 导入只读取本地文件源码中真实存在的结构化 `<table>`，例如：

```html
<table>
  <tr><th>时间</th><th>联赛</th><th>主队</th><th>客队</th><th>来源</th></tr>
  <tr><td>2026-01-01 19:30</td><td>测试联赛</td><td>甲队</td><td>乙队</td><td>本地文件</td></tr>
</table>
```

- 解析器不会执行 JavaScript、加载图片或其他外部资源、联网、抓取网站，也不会从脚本或自然语言中猜测比赛；因此只有动态网页占位而源码中没有表格的文件无法导入。
- 文件中有多个表格时，会选择必填字段齐全且可识别字段最多的比赛表。
- 支持 UTF-8（含 BOM）并回退 GB18030，支持 HTML 实体、嵌套文字标签及 `<br>`。
- 为避免静默产生列错位，含 `rowspan` 或 `colspan` 合并单元格的候选 HTML 表格会被明确拒绝；请先取消合并后再导入。

### 截图图片 OCR 与校对

支持本地 `.jpg`、`.jpeg` 和 `.png` 表格截图。Windows 发布包包含 RapidOCR、ONNX Runtime 以及检测、方向分类和中英文识别模型，**不要求用户安装 Tesseract、Office 或浏览器，首次运行也不会下载模型或调用联网服务**。

1. 在导入页选择截图后，程序会显示 OCR 进度，并对图片做灰度、对比度增强和适度放大。
2. OCR 根据文字框位置将内容按行列聚类，识别结果进入可编辑的“截图识别预览/校对”表格，绝不会识别完就静默写入数据库。
3. 请核对时间、联赛、主队、客队、来源及赔率。低置信度或缺少必填内容的单元格会标红，缺少必填字段时无法确认；取消对话框不会写入任何记录。
4. 如果原截图没有来源列，程序只会如实填入 `截图OCR:<原文件名>`，用户仍可编辑；不会补造比赛时间、球队或赔率。

OCR 不可能对所有图片达到 100% 准确。它面向清晰、完整、横平竖直的表格截图；模糊、反光、字号过小、严重裁剪、没有可确认表头、内容互相覆盖或无法可靠分列的图片会被拒绝，不会产生比赛记录。建议使用原始分辨率截图，完整保留表头和每列边界，避免聊天软件二次压缩；必要时先裁掉无关背景、校正旋转，并提高文字与背景的对比度。赔率无法确认时应保持为空，不要凭猜测填写。

仓库的 `data/demo_sample_data.csv` **仅用于软件测试，不代表真实比赛信息**。它不会自动进入数据库，须由用户主动导入。

## 测试

```bash
python -m pytest
```

覆盖隐含概率、去水概率、EV、Kelly、异常赔率、预测概率总和、串关组合、CSV/XLSX/HTML 导入、OCR 几何分列与校对保护及 SQLite 保存。Windows 构建还会运行 `python -m scripts.ocr_smoke_test`，使用随包模型实际识别一张本地生成的清晰表格图片；测试与构建过程不会下载模型。

## Windows EXE 打包

在已安装 Python 3.11 的 Windows 10/11 电脑双击 `build_windows.bat`。脚本会创建虚拟环境、安装依赖，依次运行 pytest 和端到端 smoke；任何检查失败都会立即停止。检查通过后使用 `football_jc_onefile.spec` 生成单文件 `dist\FootballJCAssistant.exe`，无需在旁边保留 Python 或依赖目录。原有 `football_jc.spec` 继续作为 onedir 回退方案。


Windows 自动构建全程强制使用 UTF-8，确保中文日志与中文界面测试在 Windows Runner 上稳定执行。
GitHub Actions 的 `.github/workflows/build-windows.yml` 会在 pull request、`main` 分支 push 或手工触发时，使用 Windows Server 和 Python 3.11 实际执行测试、smoke、单文件构建、EXE 存在性校验，并上传名为 `FootballJCAssistant-Windows` 的构建产物。非 Windows 构建不能代替这项 Windows CI 验证。

### 用户数据位置

- Windows：`%LOCALAPPDATA%\FootballJCAssistant\football.db`
- Linux：`${XDG_DATA_HOME:-~/.local/share}/FootballJCAssistant/football.db`

应用会自动创建目录。测试仍可向 `Database(path=...)` 传入临时路径，不会污染用户数据库。

## 当前限制与后续范围

- 尚未接入实时网络数据、PDF 或通用文档 OCR；不会抓取博彩网站或绕过反爬。图片 OCR 仅面向含明确表头和规则列布局的比赛表格截图。
- 暂无 Poisson、Elo、机器学习模型、赛果回填和完整回测。
- 亚盘目前保存和展示导入值，尚无盘口走势模型。
- 投注组合核心算法已完成，批量候选筛选与保存界面仍需增强。
- 胜平负已可计算；让球胜平负、比分、总进球、半全场的完整结算和专用界面留待后续。

请将本软件用于数据学习与辅助分析，理性决策并遵守所在地法律法规。
