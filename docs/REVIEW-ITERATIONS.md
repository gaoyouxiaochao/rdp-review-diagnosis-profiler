# 迭代修改记录

> 每轮记录：修改内容 → 验证命令 → 验证结果。基线见 `docs/REVIEW.md`。

## Round 1 —— P0-1 订单块方向反转（2026-10-14）

**修改**：
- `rdp/engines/smc.py::_order_blocks`：扫描条件反转。旧逻辑"是反向 K 线就继续往前退"，
  会停在同向 K 线；新逻辑"不是反向 K 线才往前退"，取**最近一根反向 K 线**作为订单块。
- 证据新增 `ob_candle`（bearish/bullish）字段，便于审计。
- 新增 `tests/test_rdp.py::test_order_block_is_opposite_candle`：
  断言 BULL 订单块必须是阴线、BEAR 必须是阳线。

**验证**：`python -m pytest tests/ -q` → **19 passed**（18 → 19）。

**影响面**：只影响 `order_block` 信号的位置与证据链（共振维度未引用 OB），
共振分与全池结论不变。guard 因 `confirm_bars=i-j` 契约不变，仍全通过。

## Round 2 —— P0-2 时效维度恒投 +1 票（2026-10-14）

**修改**：
- `rdp/core/confluence.py::_timeliness` 重写：
  - 只统计 `SCOPE_EVENT` 的 confirmed 信号；
  - **排除 smc 的 bos/choch**（结构维度已计票，防同源重复计票）；
  - 取 `confirmed_idx` 最大的一条，距今 ≤ `FRESH_BARS(10)` 根投其方向票，超窗 0 票；
  - 该最近事件若已失效投 -1。
- 函数签名改为 `_timeliness(all_signals, last_idx)`，`evaluate()` 传入 `len(bars)-1`。
- 新增 `tests/test_rdp.py::test_timeliness_votes_by_recency_not_any_signal`：
  覆盖"老事件 0 票 / 新鲜多头 +1 / 新鲜空头 -1 / 结构事件不计 / 已失效 -1"五分支。

**验证**：`python -m pytest tests/ -q` → **20 passed**；`python -m rdp.cli --all` → guard 196/196。

**影响面（共振分布修正前后，全池 196 只）**：

| 指标 | 修正前（失真） | 修正后 |
|---|---|---|
| 看涨共振 | 45 | 32 |
| 看跌共振 | 24 | 92 |
| 多空分歧 | 126 | 70 |
| 无有效共振 | 1 | 2 |
| 时效票 | 恒 +1（195 只） | +1:61 / 0:32 / -1:103 |

**解读**：修正后"看跌共振"显著增多、"多空分歧"减半——此前 timeliness 恒 +1
与真实的空头投票打架，人为制造出大量"分歧"。新分布与 2026-10-13 近期市场偏弱
的观感一致。**已发布的三件套已按修正后口径重新生成。**

## Round 3 —— P1 批量（loader / fetch / pattern）（2026-10-14）

**修改**：
- `loader.data_quality`（P1-1）：`long_gaps` 改用 `datetime` 真实自然日差，阈值 10 天，
  并截断到前 8 条 + `long_gaps_total` 计数（P2-7）。
- `loader.data_quality`（P1-2）：`limit_like` 改为 `high==low and volume>0`
  （旧条件 `range_>0 and high==low` 永假）。
- `loader.load_bars`（P2-6）：重复日期去重（保留先到者）。
- `tools/fetch_klines.py`（P1-3）：http→https；新增全局限流（间隔 0.25s）；
  指数退避 (1s/2s/4s)；RETRY 2→3；WORKERS 8→4；`amount` 由伪造 0.0 改 `None`（P2-4）。
- `pattern._double_tops_bottoms`（P1-4）：新增 `MIN_GAP=8` 最小间隔约束，
  `LEVEL_TOL=0.05` 提为常量。

**验证**：`pytest` → **20 passed**；`python -m rdp.cli --all` → guard 196/196。

## Round 4 —— 清理死参数 + 报告信号多样性（2026-10-14）

**修改**：
- `guard.check_engine`（P1-5 前半）：删除从未使用的死参数 `ratios`。
- `render_html._signal_rows`（P2-5）：改为"6 引擎各取最强一条 + 按 strength 补足"，
  防止 pattern 吞没信号刷屏挤掉 wyckoff/dow 阶段判定；展示条数 8→10。

**说明（P1-5 后半的取舍）**：`check_engine_result` 在 as_of=末根时 `full` 与 `res`
内容相同，理论上可省 1/7 次计算；但真正复用需要改动 `check_engine` 的返回类型并波及
全部测试，收益微小、回归风险不值得，故保留，记入遗留问题。

**验证**：`pytest` → 20 passed；E2E 重跑 guard 196/196。

## Round 5 —— 补边界测试（2026-10-14）

**新增测试 5 条**（18 → 25）：
- `test_loader_missing_file_raises`：缺文件必须抛 `DataMissing`，不许静默返回空；
- `test_loader_dedupes_duplicate_dates`：重复日期去重；
- `test_data_quality_year_crossing_gap`：跨年缺口（P1-1 回归）；
- `test_data_quality_limit_like`：一字板计数（P1-2 回归）；
- `test_wyckoff_insufficient_bars`：<60 根必须报"数据不足"。

**验证**：`python -m pytest tests/ -q` → **25 passed**。


## Round 7 —— 交付核验：guard 专项复核 D1/D2 修复 + 干净环境测试加固（2026-10-14）

**背景**：外部专家评审前交付核验，对 `core/guard.py` 做专项复核，先复现后修复，不做无关重构。

### 缺陷说明（修复前）

- **D1（P1）历史 `--as-of` 误报**：`check_engine` 拿**全量**结果 `full.signals`
  套 `confirmed_idx <= as_of_idx` 上界。历史基准日场景下，信号在 as_of 之后才确认
  完全合法（截断结果里它仍是 candidate），却被判"确认日超出 as_of"→ 体检 FAIL。
  影响范围：所有 `--as-of < 最新交易日` 的运行。
  复现：`test_d1_historical_as_of_no_false_positive`（修复前失败）。
- **D2（P2）confirmed/invalidated 同级漏检**：`STATE_RANK` 把两者都定为 1，
  "截断时 invalidated、更长历史变 confirmed"这类失效复活型重绘检测不到。
  影响范围：防未来函数体检的单调性断言存在盲区。
  复现：`test_d2_invalidated_then_confirmed_is_repaint`（修复前失败）。

### 修改（最小范围）

- `schema.py`：`STATE_RANK` 改为 candidate=0 / confirmed=1 / **invalidated=2**
  （仅 guard 使用，无其他消费方，已 grep 确认）。
- `guard.py`：
  - `check_confirm_consistency(signals, as_of_idx=None)`：as_of 上界改为可选；
    全量结果只校验时序合法性（确认≥形成+confirm_bars、失效≥形成），
    as_of 上界只施加在**截断口径**结果上（D1 修复）。
  - 铁律 3 文档同步为 candidate→confirmed→invalidated 单向推进。

### 干净环境测试加固（核验中发现）

- `test_confluence_votes_are_single_sourced`：依赖本地行情缓存，干净克隆必挂 →
  改为无缓存时 `pytest.skip`（标注为集成测试）。
- `test_loader_dedupes_duplicate_dates`：`data/klines/` 不存在时写文件失败 →
  补 `mkdir(parents=True, exist_ok=True)`。

### 新增场景测试（25 → 29）

- `test_d1_historical_as_of_no_false_positive` / `test_d2_invalidated_then_confirmed_is_repaint`：上述缺陷回归。
- `test_all_engines_survive_truncated_data`：短数据（<MIN_CUT_BARS）下六引擎不崩溃、体检降级不误判。
- `test_confluence_invalidated_event_votes_against`：已失效事件时效票必须为 -1。

**验证**：`python -m pytest tests/ -q` → **28 passed, 1 skipped**（干净环境，无行情缓存；
skipped 为集成测试）。D 盘全量环境（有缓存）复跑确认 guard 196/196 不受影响。
