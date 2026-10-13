# 全面评审报告（Round 0 · 评审后、迭代前基线）

> 评审对象：`复盘诊断画像模块`（rdp v1.0，6 引擎，196 标的）
> 评审维度：代码质量 / 架构设计 / 性能 / 安全性 / 可维护性 / 测试覆盖
> 分级：**P0 正确性缺陷**（必须修）｜**P1 重要缺陷**（应当修）｜**P2 改进建议**（可选）

> **状态（2026-10-14）**：P0 × 2、P1 × 6 已全部修复（见 `docs/REVIEW-ITERATIONS.md`），
> 【基线，评审时点读数】25 条测试全过，guard 196/196。P2 部分落地，其余转入"遗留问题"。
> 【最新状态】Round 7（交付核验）后：29 条测试（28 passed + 1 skipped 集成项），新增 D1/D2 修复，详见 `REVIEW-ITERATIONS.md` Round 7。

---

## 一、总体结论

| 维度 | 评级 | 说明 |
|---|---|---|
| 代码质量 | B | 契约清晰、命名可读；但存在 2 处 P0 逻辑缺陷 |
| 架构设计 | A- | 分层干净（loader→engines→guard→confluence→scorecard→report），契约统一 |
| 性能 | B+ | 全池 < 2s；有两处 O(N²) 可优化，guard 存在一次冗余计算 |
| 安全性 | A- | 无密钥、无注入面、HTML 全 escape；行情为 http 明文（公开数据） |
| 可维护性 | B+ | 单一职责好；测试缺口在边界与具体投票值 |
| 测试覆盖 | B | 18 条，因果性/guard 覆盖好；loader/wyckoff 边界、confluence 数值、OB 语义缺断言 |

**结论：可交付，但必须先修 2 个 P0 再推外部评审。** 其中 P0-2 会让共振分被系统性抬高，直接影响已发布三件套的数字。

---

## 二、P0 正确性缺陷

### P0-1 `smc._order_blocks` 方向逻辑完全反转

```python
while j >= 1 and ((s.direction == BULL and bars[j].close < bars[j].open)
                  or (s.direction == BEAR and bars[j].close > bars[j].open)):
    j -= 1
```

- **问题**：向上突破（BULL）的订单块定义是"突破前**最后一根阴线**"。当前 while 条件是
  "只要 bars[j] 是阴线就继续往前退"——退过所有阴线，停在阳线，**取了一根阳线当订单块**。
  方向完全反了。
- **影响**：所有 `order_block` 信号的位置与价格区间都是错的（10,681 条 smc 信号中
  order_block 全部失真）。由于 confluence 只用 BOS/CHoCH 不用 OB，**不影响共振分**，
  但影响画像中 OB 证据链的可信度。
- **修法**：扫描方向反转——从 i-1 往前找**最近一根反向 K 线**即停。

### P0-2 `confluence._timeliness` 死表达式，时效维度恒投 +1 票

```python
forming = [s for s in all_signals
           if s.state == CONFIRMED and s.confirmed_idx is not None
           and s.confirmed_idx >= len(all_signals) * 0]   # ← *0 恒为 0，条件恒真
```

- **问题**：`len(all_signals) * 0` 恒为 0，于是 `forming == confirmed`；只要历史上有
  任何一条 confirmed 信号，时效维度就返回 `close_confirmed, +1`。
- **影响**：**全池 196 只的共振分被系统性 +1**。这是看涨共振 45 vs 看跌共振 24
  偏多分布的主要推手之一，已发布三件套的"共振分/结论"数字失真。
- **修法**：时效改为"最近一条**非结构类** confirmed 事件距今的根数"，并按其方向投票：
  距今 ≤ 10 根投其方向，否则 0 票；最近事件已失效投 -1。

---

## 三、P1 重要缺陷

| 编号 | 位置 | 问题 | 修法 |
|---|---|---|---|
| P1-1 | `loader.data_quality` | `long_gaps` 用"月差×31+日差"算间隔，**跨年算错**（12→01 月差 -11） | 用 `datetime.strptime` 真实天数差 |
| P1-2 | `loader.data_quality` | `limit_like` 条件 `range_>0 and high==low` 永假（high==low 时 range_=0），指标恒 0 | 改为 `high==low and volume>0`（一字板有成交） |
| P1-3 | `tools/fetch_klines.py` | 用 http（已被腾讯 302→https，且 196 连抓触发 WAF 501）；无节流；RETRY=2 太少 | 改 https + 每次请求间隔 + 指数退避 + 失败清单 |
| P1-4 | `pattern._double_tops_bottoms` | 两顶/两底之间无最小间隔约束，相邻摆动点太近会误判 | 加 `b.idx - a.idx >= MIN_GAP` |
| P1-5 | `guard.check_engine` | 形参 `ratios` 从未使用（死参数）；且 `check_engine_result` 在 as_of=末根时 full 与 res 重复计算一次 | 删死参数；idx==len-1 时复用 full 作 res |
| P1-6 | `tests/` | 缺：loader 边界（缺文件/空 bars）、wyckoff <60 根边界、timeliness 具体投票值、OB 方向语义断言 | 补测试 |

## 四、P2 改进建议

| 编号 | 位置 | 建议 |
|---|---|---|
| P2-1 | `smc._last_structure` | 每根 bar 重扫 `known_h/known_l`，O(N×P)；可改增量维护，O(N) |
| P2-2 | `wyckoff._range_of` | 每根重算 min/max，O(N×W)；可用单调队列 O(N) |
| P2-3 | `smc._last_structure` | 用 high/low 突破判 BOS，SMC 通行做法是 close 突破；当前定义更敏感，建议文档化 |
| P2-4 | `fetch_klines` | `amount` 恒写 0，字段无效，应删或标注 |
| P2-5 | `render_html._signal_rows` | 按 strength 排序取前 8，会被 engulfing(0.6) 挤掉 phase 信号；建议按"每引擎各取最强"保多样性 |
| P2-6 | `loader.load_bars` | 无重复日期去重、无日期格式校验 |
| P2-7 | `data_quality.long_gaps` | 全量列出可能很长，截断到前 N 条 |

## 五、安全性检查

- 无密钥/凭据硬编码 ✓
- HTML 输出全部走 `html.escape`，无 XSS 注入面 ✓
- JSON 只读本机自己写的文件，无反序列化外部输入 ✓
- 行情为公开数据的 http 明文接口（P1-3 已列改 https）
- 无日志泄露敏感信息 ✓

## 六、性能分析

| 模块 | 复杂度 | 评估 |
|---|---|---|
| indicators 全部 | O(N) | 优 |
| swing_pivots | O(N×K)，K=left+right=6 | 优 |
| smc._last_structure | O(N×P) 重扫 pivot | 可优化（P2-1） |
| wyckoff._range_of | O(N×W)，W=50 | 可优化（P2-2） |
| guard | 每引擎 6 次重算（5 切点+全量）+res 1 次 | 末根时 full==res 可省 1 次（P1-5） |
| 全池总耗时 | ≈ 3 s（196 只×6 引擎×7 次） | 可接受 |

## 七、测试覆盖缺口

已覆盖：指标因果性 5 项、pivot 确认、guard 抓作弊/确认违规/非空转/状态量排除、6 引擎合成+真实样本过 guard、confluence 维度唯一性、scorecard 范围、契约完整性。

缺口（P1-6 补齐）：loader 异常路径、wyckoff 数据不足、timeliness 投票数值、OB 方向、双顶最小间隔。
