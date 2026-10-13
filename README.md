# 复盘诊断分析画像模块（RDP）

> Review & Diagnosis Profiling —— 纯技术面复盘诊断，**不接交易数据、不做回测、不给投资建议**。
> 全部代码独立自研，未复用本机任何其他目录的既有代码。

## 0. 项目背景与评审状态

- **背景**：源于一次 8 模块技术分析系统的开源方案比选（24 个 GitHub 候选库），
  目标是单独抽出一套**因果、可审计、无未来函数**的复盘诊断能力，独立成模块。
- **评审状态（2026-10-14）**：已做一轮六维全面评审（`docs/REVIEW.md`），
  发现并修复 **P0 × 2**（订单块方向反转、时效维度恒投+1）与 **P1 × 6**，
  迭代记录见 `docs/REVIEW-ITERATIONS.md`。最新（Round 7 后）：pytest 28 passed + 1 skipped
  （干净环境；集成测试需行情缓存），防未来函数体检 196/196。
  **外部评审专家请从 `docs/EXPERT-HANDOFF.md` 开始。**
  **欢迎外部专家基于 `docs/REVIEW.md` 遗留清单继续评审。**

## 1. 它做什么

对指定标的池的每一只股票，跑一套**因果、可验证**的技术诊断流水线，输出一份"画像"：

- 6 个技术引擎各自产出**带状态的信号**（候选 / 已确认 / 已失效），每条信号都带**证据链**（用了哪几根 K 线、什么价格、什么阈值）；
- 一个**防未来函数闸门**（M2）逐一验证每个引擎——不是嘴上说说，而是把历史切成 5 个观察点，
  在每个点上用"只到那一天的数据"重算一遍，和"用完整数据算出来的"逐条对拍，
  只要出现任何不一致就判 FAIL；
- 一个**多规则共振投票**（M4）：趋势 / 结构 / 量价 / 时效性四个维度独立投票，同一根 K 线上相关的指标不重复计票；
- 一个**六维评分卡**（M3），评的是"本次诊断本身可不可信"，不是给股票打分。

最终交付 **HTML + JSON + Excel** 三件套。

## 2. 目录结构

```
复盘诊断分析画像模块/
├─ 00_评估方案与建议.md / .html     # 引入开源机制的评估报告（阶段 0）
├─ README.md                        # 本文件
├─ data/
│  ├─ targets.json                  # 196 只标的（来自股权激励_2026中报补全_R到U.xlsx）
│  └─ klines/{code}.json            # 前复权日线，每只一份
├─ docs/
│  ├─ FETCH_SPEC.md                 # 行情抓取与落地规范
│  └─ OPEN-DECISIONS.md             # 待定项与技术债
├─ tools/fetch_klines.py            # 行情抓取（腾讯公开接口，前复权）
├─ rdp/
│  ├─ schema.py                     # 数据契约（Bar / Signal / EngineResult / GuardReport / Profile）
│  ├─ core/
│  │  ├─ indicators.py              # 纯 Python 指标：SMA/EMA/RSI/ATR/MACD/摆动 pivot/量能MA
│  │  ├─ loader.py                  # 唯一行情入口 + 数据质量体检
│  │  ├─ guard.py                   # 防未来函数闸门（walk-forward 截断对拍）
│  │  ├─ confluence.py              # 四维度共振投票
│  │  ├─ scorecard.py               # 六维评分卡
│  │  └─ pipeline.py                # 编排：单只 build / 全池 build_all
│  ├─ engines/
│  │  ├─ volume_profile.py          # 滚动筹码分布 POC / VAH / VAL
│  │  ├─ smc.py                     # 市场结构：BOS / CHoCH / 订单块 / FVG
│  │  ├─ divergence.py              # RSI 背离（常规 + 隐藏）
│  │  ├─ pattern.py                 # K 线形态 + 双顶双底结构
│  │  ├─ wyckoff.py                 # 交易区间 / Spring / Upthrust / 放量无果
│  │  └─ dow.py                     # 道氏 HH-HL 序列 / 次级折返 / 量能确认
│  ├─ report/                       # styles.py / render_excel.py / render_html.py
│  └─ cli.py                        # 命令行入口
├─ tests/test_rdp.py                # 13 条回归测试
└─ output/                          # 产物：profiles.json / xlsx / html
```

## 3. 快速开始

```bash
cd <模块根目录>
set PYTHONIOENCODING=utf-8

# 0) 安装依赖（运行+测试）
pip install -r requirements-dev.txt

# 1) 抓行情（已有则跳过；--force 强制重抓）
python tools/fetch_klines.py --all

# 2) 跑诊断并出三件套
python -m rdp.cli --all

# 单只调试
python -m rdp.cli --code 002245

# 换基准日
python -m rdp.cli --all --as-of 2026-09-30

# 3) 回归测试
python -m pytest tests/ -q
```

产物落在 `output/`：
- `profiles.json` —— 全量结构化画像（引擎指标、信号明细、闸门报告、共振、评分卡）
- `复盘诊断画像_汇总.xlsx` —— 5 个表：画像总览 / 信号明细 / 引擎指标 / 防未来函数体检 / 六维评分卡
- `复盘诊断画像报告.html` —— 可排序可筛选的全池排名表 + Top24 详情卡 + 方法论与免责声明

> **首次运行说明**：诊断命令依赖本地行情缓存 `data/klines/*.json`，请先执行 `python tools/fetch_klines.py --all`（全池约 196 只，内置限流与重试，腾讯行情接口偶发 WAF 限流属预期，重跑即可续抓）。股票池清单 `data/targets.json` 已随仓库提交，无需手工准备。

## 4. 当前验收结果（基准日 2026-10-13）

| 项 | 结果 |
|---|---|
| 标的数 | 196 |
| 引擎数 | 6 |
| 行情抓取 | ok=196 / skip=0 / fail=0 |
| 画像构建失败 | 0 |
| **防未来函数体检** | **196 / 196 全通过**（5 个历史切点对拍，非空转） |
| 信号总数 | 26,734（均每只 136.4） |
| 回归测试 | 18 passed |

## 5. 核心机制说明

### M1 信号三态机
`candidate → confirmed → invalidated`。每条 `Signal` 记录 `formed_at/formed_idx`（形态成形）、`confirmed_at/confirmed_idx`（确认）、`invalidated_at/invalidated_idx`（失效）以及 `evidence`（证据）。只有 `confirmed` 的信号才参与共振投票。

### M2 防未来函数闸门（本模块的立身之本）
`rdp/core/guard.py` 的 `check_engine()`：**多切点 walk-forward 对拍**。

1. 在 as_of 的 55% / 70% / 82% / 92% / 100% 五个历史位置各取一个观察点 t；
2. 用**只到 t 的 K 线**重跑引擎，与"用完整数据跑出来的"结果逐条对拍；
3. 只比 `event` 类信号（`state` 类状态量天然落在最后一根 K 线，比了必误报，已排除）；
4. 只比"已跨过确认窗"的信号：`formed_idx + confirm_bars <= t`；
5. 状态只允许单向推进（candidate→confirmed 合法，confirmed→candidate 判重绘）。

测试里专门喂了一个故意偷看未来的引擎 `_cheater`，闸门确实抓出来了。
另有 `test_guard_is_not_vacuous` 断言切点数量，防止闸门退化成空转。

> **为什么要多切点**：早期实现只拿"截断到 as_of"的数据和"全量"比，而 pipeline 传入的
> 数据本身就已截断，两边完全相同，体检恒为通过。修正后立刻暴露出 37 只标的的
> SMC 订单块契约问题（订单块位置在第 j 根、却要等第 i 根突破才被识别，
> 原来 `confirm_bars` 写成 0）。详见 `docs/OPEN-SOURCE-REFERENCE.md`。

### M3 六维评分卡
沿用比选阶段权重：算法完整性 25 / 信号可靠性 20 / 工程可集成性 20 / 测试与验证 15 / A股适配性 10 / 许可证与维护 10。
**注意**：评分对象是"这次诊断可不可信"，不是股票好不好。

### M4 共振投票
趋势（MA20/MA60）、结构（SMC）、量价（量能 MA20 + 背离）、时效性四个维度独立出票。
形成有效共振需同时满足：|共振分| ≥ 2 且至少 2 张同向票。

## 6. 边界与红线

- **不接任何交易/持仓数据**，本模块不知道你买了什么。
- **不做回测**，不产出任何"策略收益""胜率"类数字。
- **不构成投资建议**。所有输出只描述技术状态。
- **未复用本机其他目录的代码**，所有引擎/指标/渲染均为独立编写。
- 生产库、其他项目目录一律只读，脚本与产物只落在本模块目录内。
