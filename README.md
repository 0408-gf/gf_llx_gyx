# 足球竞彩分析助手（MVP）

面向 Windows 10/11 的中文桌面足球比赛预测与中国竞彩足球分析工具。程序只分析用户真实导入的数据；缺失字段显示“暂无数据”，不会编造比赛、赔率、伤停、球队状态或资金流向。预测和组合均为可解释的模型建议，**不代表必胜，也不承诺盈利**。

## 已完成功能

- PySide6 中文桌面框架，包含仪表盘、导入、比赛列表、单场分析、概率预测、欧赔、亚盘、EV、投注组合、资金管理、历史和设置 12 个功能区。
- Windows EXE 的窗口标题“足球竞彩分析助手 MVP”、全部导航、操作按钮、字段名称、提示和错误信息均使用中文；EV（期望值）、Kelly（凯利资金管理）等通用行业缩写会保留，并在界面中配合中文说明。
- CSV、制表符 TXT 和 XLSX 导入；中英文字段识别、必填检查、日期及数字转换、清晰错误提示。赔率允许为空。
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

支持 `.csv`、`.xlsx` 和 `.txt`（逗号或制表符分隔）。首行是字段名。必填字段为比赛时间、联赛、主队、客队、数据来源；其余赔率均可留空。

```text
比赛时间,联赛,主队,客队,主胜赔率,平局赔率,客胜赔率,亚洲让球盘口,主队亚盘赔率,客队亚盘赔率,大小球盘口,大球赔率,小球赔率,数据来源,更新时间
```

也支持对应英文名：`match_time, league, home_team, away_team, home_odds, draw_odds, away_odds, asian_line, asian_home_odds, asian_away_odds, total_line, over_odds, under_odds, source, updated_at`。日期建议使用 `YYYY-MM-DD HH:MM`。

仓库的 `data/demo_sample_data.csv` **仅用于软件测试，不代表真实比赛信息**。它不会自动进入数据库，须由用户主动导入。

## 测试

```bash
python -m pytest
```

覆盖隐含概率、去水概率、EV、Kelly、异常赔率、预测概率总和、串关组合、CSV/XLSX 导入及 SQLite 保存。

## Windows EXE 打包

在已安装 Python 3.11 的 Windows 10/11 电脑双击 `build_windows.bat`。脚本会创建虚拟环境、安装依赖，依次运行 pytest 和端到端 smoke；任何检查失败都会立即停止。检查通过后使用 `football_jc_onefile.spec` 生成单文件 `dist\FootballJCAssistant.exe`，无需在旁边保留 Python 或依赖目录。原有 `football_jc.spec` 继续作为 onedir 回退方案。

GitHub Actions 的 `.github/workflows/build-windows.yml` 会在 pull request、`main` 分支 push 或手工触发时，使用 Windows Server 和 Python 3.11 实际执行测试、smoke、单文件构建、EXE 存在性校验，并上传名为 `FootballJCAssistant-Windows` 的构建产物。非 Windows 构建不能代替这项 Windows CI 验证。

### 用户数据位置

- Windows：`%LOCALAPPDATA%\FootballJCAssistant\football.db`
- Linux：`${XDG_DATA_HOME:-~/.local/share}/FootballJCAssistant/football.db`

应用会自动创建目录。测试仍可向 `Database(path=...)` 传入临时路径，不会污染用户数据库。

## 当前限制与后续范围

- 尚未接入实时网络数据、PDF、图片或 OCR；不会抓取博彩网站或绕过反爬。
- 暂无 Poisson、Elo、机器学习模型、赛果回填和完整回测。
- 亚盘目前保存和展示导入值，尚无盘口走势模型。
- 投注组合核心算法已完成，批量候选筛选与保存界面仍需增强。
- 胜平负已可计算；让球胜平负、比分、总进球、半全场的完整结算和专用界面留待后续。

请将本软件用于数据学习与辅助分析，理性决策并遵守所在地法律法规。
