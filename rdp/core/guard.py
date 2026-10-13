# -*- coding: utf-8 -*-
"""防未来函数闸门（机制 M2）—— walk-forward 多切点对拍。

这是整个复盘模块的可信度命门：如果某个引擎在第 i 根的信号依赖了 i 之后的数据，
那么"复盘"就是在作弊，诊断结论一律作废。

为什么必须"多切点"：
    早期实现只拿 bars[:as_of+1] 与"全量"比，而 pipeline 传入的 bars 本身就已
    截断到 as_of —— 两边数据完全相同，体检恒为通过，形同虚设。
    正确做法是：把历史切成多个观察点 t，用 bars[:t+1] 重算，与"用更长的历史
    算出来"的结果逐条对拍。只要引擎偷看了未来，边界处必然露馅。

对拍口径（三条铁律）：
    1. 只比 event 类信号。state 类信号（如筹码位置、阶段判定）天然依附于最后
       一根 K 线，任何切点下都只会落在末尾，比了必误报，故排除。
    2. 只比"已过确认窗"的信号：formed_idx + confirm_bars <= t。未过确认窗的
       信号在截断处本来就不该出现，比了也是误报。
    3. 状态只允许单向推进（candidate→confirmed→invalidated，rank 0/1/2）：
       cut 里是 candidate、full 里变成 confirmed/invalidated 合法；任何回退
       （含 invalidated→confirmed 这类"失效又复活"的重绘）判 FAIL。
"""
from __future__ import annotations

from typing import Callable

from ..schema import (
    Bar, EngineResult, GuardReport, Signal,
    CONFIRMED, SCOPE_EVENT, STATE_RANK,
)

# 观察切点：占 as_of_idx 的比例。越靠后越严格，末尾必取。
CUT_RATIOS = (0.55, 0.70, 0.82, 0.92, 1.0)
# 切点最小需要多少根 K 线（低于此值引擎会直接报"数据不足"，比了必误报）
MIN_CUT_BARS = 80


def fingerprint(s: Signal) -> str:
    """完整指纹，含状态。用于同一时点的一致性描述。"""
    return "|".join([
        s.engine, s.kind, s.direction, s.state,
        s.formed_at, str(s.formed_idx),
        str(s.confirmed_at), str(s.confirmed_idx),
        str(s.invalidated_at), str(s.invalidated_idx),
    ])


def identity(s: Signal) -> str:
    """身份指纹，不含状态。状态另走单调性校验。"""
    return "|".join([s.engine, s.kind, s.direction, s.formed_at, str(s.formed_idx)])


def _rank(state: str) -> int:
    return STATE_RANK.get(state, 0)


def check_confirm_consistency(
    signals: list[Signal], as_of_idx: int | None = None
) -> tuple[int, list[str]]:
    """确认时间必须 >= 形成时间 + confirm_bars；as_of_idx 非空时确认不得晚于它。

    as_of 上界只应施加在"按 as_of 截断口径"的结果上：历史 --as-of 场景下，
    信号在 as_of 之后才确认是合法的（截断结果里它仍是 candidate），
    若拿全量结果套 as_of 上界必然误报（缺陷 D1）。
    """
    bad = 0
    samples: list[str] = []
    for s in signals:
        if s.state == CONFIRMED and s.confirmed_idx is not None:
            if s.confirmed_idx < s.formed_idx + s.confirm_bars:
                bad += 1
                samples.append(f"{s.engine}/{s.kind}@{s.formed_at}: 确认早于 confirm_bars({s.confirm_bars})")
            if as_of_idx is not None and s.confirmed_idx > as_of_idx:
                bad += 1
                samples.append(f"{s.engine}/{s.kind}@{s.formed_at}: 确认日超出 as_of")
        if s.invalidated_idx is not None and s.formed_idx is not None:
            if s.invalidated_idx < s.formed_idx:
                bad += 1
                samples.append(f"{s.engine}/{s.kind}@{s.formed_at}: 失效早于形成")
    return bad, samples[:5]


def _cut_points(as_of_idx: int) -> list[int]:
    """生成观察切点。数据太短时降级为只做末点校验。"""
    if as_of_idx + 1 < MIN_CUT_BARS:
        return [as_of_idx] if as_of_idx > 0 else []
    lo = max(MIN_CUT_BARS - 1, int(as_of_idx * CUT_RATIOS[0]))
    pts = sorted({int(as_of_idx * r) for r in CUT_RATIOS if int(as_of_idx * r) >= lo})
    if as_of_idx not in pts:
        pts.append(as_of_idx)
    return [p for p in pts if p > 0]


def _eligible(sigs: list[Signal], t: int) -> list[Signal]:
    """可被对拍的信号：event 类，且已跨过确认窗。"""
    return [s for s in sigs
            if s.scope == SCOPE_EVENT and s.formed_idx >= 0
            and s.formed_idx + s.confirm_bars <= t]


def check_engine(
    name: str,
    fn: Callable[[list[Bar]], EngineResult],
    bars: list[Bar],
    as_of_idx: int,
) -> GuardReport:
    """对一个引擎做 walk-forward 全身体检。

    注意：bars 必须是**未经截断**的完整序列，as_of_idx 是诊断基准日下标。
    若调用方先截断了 bars，体检会退化成单点空转 —— 这是本函数要消灭的病。
    """
    full = fn(bars)
    truncated = fn(bars[: as_of_idx + 1])
    cuts = _cut_points(as_of_idx)

    mismatched = 0
    regressions = 0
    samples: list[str] = []

    for t in cuts:
        cut = fn(bars[: t + 1])
        fe = {identity(s): s for s in _eligible(full.signals, t)}
        ce = {identity(s): s for s in _eligible(cut.signals, t)}

        diff = sorted(set(fe) ^ set(ce))
        if diff:
            mismatched += len(diff)
            samples.append(f"切点{t}({bars[t].date}) 不一致 {len(diff)} 条，例：{diff[0]}")
            continue

        # 状态单调性：只允许向前推进，不允许回退
        back = 0
        for k, cs in ce.items():
            fs = fe[k]
            if _rank(fs.state) < _rank(cs.state):
                back += 1
                if back <= 2:
                    samples.append(
                        f"切点{t} 状态回退 {cs.kind}@{cs.formed_at}: {cs.state}->{fs.state}")
        regressions += back

    # 时序合法性：形成/确认/失效的先后关系对全量结果校验（与 as_of 无关）；
    # as_of 上界只对截断口径的结果校验（D1 修复：历史 as_of 不误报）。
    confirmed_viol, csamples = check_confirm_consistency(full.signals)
    tv, tsamples = check_confirm_consistency(truncated.signals, as_of_idx)
    confirmed_viol += tv
    samples = (samples + csamples + tsamples)[:8]

    passed = (mismatched == 0 and regressions == 0 and confirmed_viol == 0)
    if not full.ok and cuts:
        samples.append(f"engine_error: {full.error}")

    return GuardReport(
        engine=name,
        passed=passed,
        total_signals=len(full.signals),
        mismatched=mismatched,
        lookahead_violations=mismatched,
        confirm_violations=confirmed_viol + regressions,
        samples=samples,
    )


def check_engine_result(
    name: str,
    fn: Callable[[list[Bar]], EngineResult],
    bars: list[Bar],
    as_of_idx: int,
) -> tuple[GuardReport, EngineResult]:
    """体检 + 取结果。结果按 as_of 截断口径计算，体检按全量口径对拍。"""
    rep = check_engine(name, fn, bars, as_of_idx)
    res = fn(bars[: as_of_idx + 1])
    return rep, res
