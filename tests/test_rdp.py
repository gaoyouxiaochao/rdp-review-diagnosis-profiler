# -*- coding: utf-8 -*-
"""复盘诊断画像模块测试。重点：因果性、防未来函数、确认约束、不重复计票。"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rdp.schema import (Bar, EngineResult, Signal, CONFIRMED, BULL,            # noqa: E402
                        SCOPE_STATE)
from rdp.core import indicators as ind                                          # noqa: E402
from rdp.core.guard import (check_engine, check_engine_result,                  # noqa: E402
                            check_confirm_consistency, _cut_points)
from rdp.core.pipeline import build_all, ENGINE_FNS                             # noqa: E402
from rdp.engines import (volume_profile, smc, divergence, pattern,              # noqa: E402
                         wyckoff, dow)

ALL_ENGINES = (volume_profile.run, smc.run, divergence.run, pattern.run,
               wyckoff.run, dow.run)


def synth(n: int = 160, seed: int = 7) -> list[Bar]:
    rnd = random.Random(seed)
    px, out = 10.0, []
    for i in range(n):
        o = px
        px *= (1 + rnd.uniform(-0.03, 0.031))
        c = px
        h = max(o, c) * (1 + rnd.uniform(0, 0.02))
        l = min(o, c) * (1 - rnd.uniform(0, 0.02))
        out.append(Bar(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", round(o, 2), round(h, 2),
                       round(l, 2), round(c, 2), 100000 + rnd.randint(0, 50000), 1e8))
    return out


BARS = synth()


# ---------- 指标因果性 ----------

def test_sma_causal():
    vals = [b.close for b in BARS]
    full = ind.sma(vals, 20)
    for cut in (40, 80, 120):
        part = ind.sma(vals[:cut], 20)
        assert part == full[:cut], f"sma 在截断 {cut} 处不一致（存在未来函数）"


def test_ema_causal():
    vals = [b.close for b in BARS]
    full = ind.ema(vals, 12)
    for cut in (40, 80, 120):
        assert ind.ema(vals[:cut], 12) == full[:cut]


def test_rsi_causal_and_range():
    vals = [b.close for b in BARS]
    full = ind.rsi(vals, 14)
    assert ind.rsi(vals[:100], 14) == full[:100]
    got = [v for v in full if v is not None]
    assert all(0.0 <= v <= 100.0 for v in got)


def test_macd_causal():
    vals = [b.close for b in BARS]
    full = ind.macd(vals)
    part = ind.macd(vals[:100])
    assert part.dif == full.dif[:100]


def test_pivots_need_right_confirm():
    pivots = ind.swing_pivots([b.high for b in BARS], [b.low for b in BARS], 3, 3)
    for p in pivots:
        assert p.confirmed_idx == p.idx + 3
    # 末尾 3 根之内不应产生"已可确认"的摆动点
    assert all(p.confirmed_idx <= len(BARS) - 1 for p in pivots)


# ---------- 防未来函数闸门 ----------

def _cheater(bs: list[Bar]) -> EngineResult:
    """故意偷看最后一根（未来）数据的引擎。"""
    return EngineResult("cheat", True, signals=[Signal(
        engine="cheat", kind="peek", direction=BULL if bs[-1].close > bs[-2].close else "bear",
        state=CONFIRMED, formed_at=bs[-3].date, formed_idx=len(bs) - 3,
        confirmed_at=bs[-3].date, confirmed_idx=len(bs) - 3,
        confirm_bars=0, price=bs[-1].close, evidence={"peek": bs[-1].close})])


def test_guard_catches_lookahead():
    rep = check_engine("cheat", _cheater, BARS, len(BARS) - 20)
    assert rep.passed is False, "闸门未能识别偷看未来数据的引擎"
    assert rep.mismatched > 0


def test_guard_is_not_vacuous():
    """闸门必须真的有多个观察切点，否则"全量=截断"会退化成恒通过。"""
    pts = _cut_points(len(BARS) - 1)
    assert len(pts) >= 3, f"切点太少，体检会失真: {pts}"
    # 若把 bars 先截断再体检，切点必须仍然覆盖到末尾之外的历史点
    assert max(pts) == len(BARS) - 1
    assert min(pts) < len(BARS) - 1


def test_state_signal_excluded_from_walkforward():
    """状态量天然落在最后一根K线，若参与对拍必然误报，必须被排除。"""

    def state_engine(bs: list[Bar]) -> EngineResult:
        return EngineResult("st", True, signals=[Signal(
            engine="st", kind="phase", direction=BULL, state=CONFIRMED,
            formed_at=bs[-1].date, formed_idx=len(bs) - 1,
            confirmed_at=bs[-1].date, confirmed_idx=len(bs) - 1,
            confirm_bars=0, price=bs[-1].close, scope=SCOPE_STATE,
            evidence={"v": len(bs)})])

    rep = check_engine("st", state_engine, BARS, len(BARS) - 1)
    assert rep.passed, f"状态量被误判为未来函数: {rep.samples}"


def test_guard_catches_confirm_violation():
    def bad(bs):
        return EngineResult("badc", True, signals=[Signal(
            engine="badc", kind="x", direction=BULL, state=CONFIRMED,
            formed_at=bs[-1].date, formed_idx=len(bs) - 1,
            confirmed_at=bs[-1].date, confirmed_idx=len(bs) - 1,
            confirm_bars=5, price=bs[-1].close, evidence={})])
    rep = check_engine("badc", bad, BARS, len(BARS) - 1)
    assert rep.passed is False
    assert rep.confirm_violations > 0


def test_confirm_consistency_helper():
    ok = Signal(engine="e", kind="k", direction=BULL, state=CONFIRMED,
                formed_at="d", formed_idx=10, confirmed_at="d", confirmed_idx=13,
                confirm_bars=3, price=1.0)
    bad_cnt, _ = check_confirm_consistency([ok], 20)
    assert bad_cnt == 0
    too_early = Signal(engine="e", kind="k", direction=BULL, state=CONFIRMED,
                       formed_at="d", formed_idx=10, confirmed_at="d", confirmed_idx=11,
                       confirm_bars=3, price=1.0)
    bad_cnt, _ = check_confirm_consistency([too_early], 20)
    assert bad_cnt == 1


# ---------- 四个引擎的 walk-forward 一致性 ----------

def test_all_engines_pass_guard_on_synth():
    for fn in ALL_ENGINES:
        rep, res = check_engine_result(fn.__module__.split(".")[-1], fn, BARS, len(BARS) - 1)
        assert res.ok, f"{fn.__module__} 未能产出结果"
        assert rep.passed, f"{fn.__module__} 未通过防未来函数体检: {rep.samples}"


def test_all_engines_pass_guard_on_real_sample():
    kdir = ROOT / "data" / "klines"
    codes = sorted(p.stem for p in kdir.glob("*.json"))[:5]
    if not codes:
        return
    for code in codes:
        raw = json.loads((kdir / f"{code}.json").read_text(encoding="utf-8"))
        bars = [Bar(b["date"], b["open"], b["high"], b["low"], b["close"],
                    b.get("volume", 0.0), b.get("amount", 0.0)) for b in raw["bars"]]
        bars.sort(key=lambda x: x.date)
        for fn in ALL_ENGINES:
            rep, _ = check_engine_result(fn.__module__.split(".")[-1], fn, bars, len(bars) - 1)
            assert rep.passed, f"{code}/{fn.__module__}: {rep.samples}"


def test_engine_registry_matches_tests():
    """防止新增引擎忘了同步流水线 / 测试。"""
    assert set(ENGINE_FNS) == {"volume_profile", "smc", "divergence", "pattern",
                               "wyckoff", "dow"}


def test_wyckoff_range_excludes_current_bar():
    """区间边界只能取 i 之前的窗口，把第 i 根算进去就是自我实现。"""
    bars = BARS
    i = 100
    hi, lo, _ = wyckoff._range_of(bars, i)
    assert hi == max(b.high for b in bars[max(0, i - wyckoff.TR_WINDOW):i])
    assert lo == min(b.low for b in bars[max(0, i - wyckoff.TR_WINDOW):i])


def test_dow_emits_full_history_not_only_latest():
    """只出"最新一条"会让 walk-forward 对拍在截断端凭空少信号，必须出全序列。"""
    res = dow.run(BARS)
    assert res.ok
    seq = [s for s in res.signals if s.scope != SCOPE_STATE]
    assert len(seq) >= 3, f"道氏序列信号太少: {len(seq)}"
    idxs = [s.formed_idx for s in seq]
    assert len(set(idxs)) == len(idxs), "同一位置重复出信号"


def test_order_block_is_opposite_candle():
    """P0-1 回归：BULL 突破的订单块必须是阴线，BEAR 突破必须是阳线，且是最近一根。"""
    res = smc.run(BARS)
    assert res.ok
    obs = [s for s in res.signals if s.kind == "order_block"]
    assert obs, "样本应至少产生一个订单块"
    for s in obs:
        j = s.formed_idx
        b = BARS[j]
        if s.direction == BULL:
            assert b.close < b.open, f"BULL 订单块取到了阳线: {s.evidence}"
        else:
            assert b.close > b.open, f"BEAR 订单块取到了阴线: {s.evidence}"
        # 订单块必须紧邻突破根之前（中间不允许再有同向突破事件）
        assert s.confirmed_idx is not None and s.confirmed_idx > j


# ---------- 共振：不重复计票 ----------

def test_confluence_votes_are_single_sourced():
    import pytest
    kdir = ROOT / "data" / "klines"
    if not kdir.is_dir() or not any(kdir.glob("*.json")):
        pytest.skip("集成测试：需要本地行情缓存 data/klines（先运行 tools/fetch_klines.py）")
    targets = json.loads((ROOT / "data" / "targets.json").read_text(encoding="utf-8"))
    profiles, _ = build_all(targets[:20])
    assert profiles
    for p in profiles:
        dims = [v["dimension"] for v in p.confluence.votes]
        assert len(dims) == len(set(dims)), f"{p.code} 同一维度被重复计票"
        assert set(dims) == {"trend", "structure", "volume_price", "timeliness"}
        assert -4 <= p.confluence.score <= 4


def test_timeliness_votes_by_recency_not_any_signal():
    """P0-2 回归：时效票必须看"最近事件的新鲜度"，不能"有任何 confirmed 就 +1"。"""
    from rdp.core.confluence import _timeliness, FRESH_BARS

    def sig(eng, kind, conf_idx, direction=BULL, invalid=False):
        return Signal(engine=eng, kind=kind, direction=direction, state=CONFIRMED,
                      formed_at="d", formed_idx=conf_idx, confirmed_at="d",
                      confirmed_idx=conf_idx, confirm_bars=0, price=1.0,
                      invalidated_idx=(conf_idx + 1 if invalid else None), evidence={})

    last = 100
    # 只有一条很老的事件 -> 0 票（旧实现会错投 +1）
    _, v, _ = _timeliness([sig("divergence", "bull_divergence", 10)], last)
    assert v == 0
    # 新鲜的多头事件 -> +1
    _, v, _ = _timeliness([sig("pattern", "bullish_engulfing", last - FRESH_BARS + 1)], last)
    assert v == 1
    # 新鲜的空头事件 -> -1
    _, v, _ = _timeliness([sig("pattern", "bearish_engulfing", last - 1, direction="bear")], last)
    assert v == -1
    # 结构事件不参与时效票（结构维度已计票，防同源重复）
    _, v, _ = _timeliness([sig("smc", "bos", last - 1)], last)
    assert v == 0
    # 最近事件已失效 -> -1
    _, v, _ = _timeliness([sig("pattern", "bullish_engulfing", last - 1, invalid=True)], last)
    assert v == -1


# ---------- 评分卡 ----------

def test_scorecard_range():
    targets = json.loads((ROOT / "data" / "targets.json").read_text(encoding="utf-8"))
    profiles, _ = build_all(targets[:20])
    for p in profiles:
        assert 0.0 <= p.scorecard.total <= 100.0
        for k, v in p.scorecard.dims.items():
            assert 0.0 <= v <= 5.0, f"{p.code} {k}={v} 越界"
        assert abs(sum(p.scorecard.weights.values()) - 100.0) < 1e-6


# ---------- 边界与异常 ----------

def test_loader_missing_file_raises():
    from rdp.core.loader import load_bars, DataMissing
    try:
        load_bars("__no_such_code__")
    except DataMissing:
        return
    raise AssertionError("缺文件必须抛 DataMissing，不能静默返回空")


def test_loader_dedupes_duplicate_dates():
    from rdp.core.loader import load_bars
    kdir = ROOT / "data" / "klines"
    kdir.mkdir(parents=True, exist_ok=True)
    dup = kdir / "__dup_test__.json"
    dup.write_text(json.dumps({"code": "__dup_test__", "bars": [
        {"date": "2026-01-02", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1},
        {"date": "2026-01-02", "open": 9, "high": 9, "low": 9, "close": 9, "volume": 9},
        {"date": "2026-01-03", "open": 2, "high": 3, "low": 2, "close": 3, "volume": 1},
    ]}, ensure_ascii=False), encoding="utf-8")
    try:
        _, bars = load_bars("__dup_test__")
        assert len(bars) == 2 and bars[0].close == 2.0, "重复日期应去重并保留先到者"
    finally:
        dup.unlink(missing_ok=True)


def test_data_quality_year_crossing_gap():
    """P1-1 回归：跨年缺口必须按真实自然日算，不能月差×31 出错。"""
    from rdp.core.loader import data_quality
    bars = [Bar("2025-12-25", 1, 2, 1, 2, 1), Bar("2026-01-08", 1, 2, 1, 2, 1)]
    q = data_quality(bars)
    assert q["long_gaps"], f"跨年 14 天缺口必须被识别: {q}"


def test_data_quality_limit_like():
    """P1-2 回归：一字板=high==low 且有成交；旧条件永假必须修。"""
    from rdp.core.loader import data_quality
    bars = [
        Bar("2026-01-02", 2, 2, 2, 2, 5000),   # 一字板（有成交）
        Bar("2026-01-03", 2, 2, 2, 2, 0),      # 无量一字（停牌，不算）
        Bar("2026-01-06", 2, 3, 1, 2.5, 5000), # 正常
    ]
    q = data_quality(bars)
    assert q["limit_like_days"] == 1, f"一字板计数错误: {q}"


def test_wyckoff_insufficient_bars():
    from rdp.core.loader import DataMissing  # noqa: F401  (保持导入一致性)
    res = wyckoff.run(BARS[:30])
    assert res.ok is False and "数据不足" in (res.error or "")


# ---------- 输出契约 ----------

def test_profile_contract_complete():
    targets = json.loads((ROOT / "data" / "targets.json").read_text(encoding="utf-8"))
    profiles, _ = build_all(targets[:10])
    need = {"code", "name", "as_of", "close", "engines", "guard",
            "confluence", "scorecard", "verdict", "risks"}
    for p in profiles:
        d = p.to_dict()
        assert need <= set(d.keys())
        for s in [x for r in p.engines.values() for x in r.signals]:
            assert s.formed_at and s.engine and s.kind
            assert s.evidence, f"{p.code} 信号缺少证据链"


# ---------- Round 7: guard 专项复核复现测试 ----------

def _mk_bars(n=160):
    from rdp.schema import Bar
    bars = []
    for i in range(n):
        bars.append(Bar(date=f"2026-{(i//28)%12+1:02d}-{(i%28)+1:02d}",
                        open=10.0, high=10.5, low=9.5, close=10.2,
                        volume=1000 + i, amount=None))
    return bars


def test_d1_historical_as_of_no_false_positive():
    """D1: 历史 --as-of 时，信号在 as_of 之后才确认（合法）不应被判违规。

    引擎行为确定性：永远在 formed=100 形成、120 确认（confirm_bars=20）。
    as_of_idx=110 时，截断结果里它是 candidate（截断口径正确），
    但全量结果里 confirmed_idx=120 > as_of_idx=110 —— 这是合法的"未来确认"，
    不应触发 "确认日超出 as_of"。
    """
    from rdp.schema import EngineResult, Signal, CONFIRMED, CANDIDATE
    from rdp.core.guard import check_engine

    def eng(bars):
        sigs = []
        if len(bars) > 100:
            confirmed = len(bars) > 120
            sigs.append(Signal(
                engine="mock", kind="brk", direction="bull",
                state=CONFIRMED if confirmed else CANDIDATE,
                formed_at=bars[100].date, formed_idx=100,
                confirmed_at=bars[120].date if confirmed else None,
                confirmed_idx=120 if confirmed else None,
                confirm_bars=20,
            ))
        return EngineResult(engine="mock", ok=True, signals=sigs, metrics={})

    bars = _mk_bars(160)
    rep = check_engine("mock", eng, bars, as_of_idx=110)
    assert rep.passed, f"D1 复现：历史 as_of 误报 -> {rep.samples}"


def test_d2_invalidated_then_confirmed_is_repaint():
    """D2: 截断时 invalidated、全量变 confirmed —— 典型的重绘，必须判 FAIL。

    当前 STATE_RANK 把 confirmed/invalidated 同级(=1)，该回退检测不到。
    """
    from rdp.schema import EngineResult, Signal, CONFIRMED, INVALIDATED
    from rdp.core.guard import check_engine

    def eng(bars):
        # 截断(101..131根)视角：信号已失效；更长历史视角：又"确认"了（重绘）
        if len(bars) <= 100:
            return EngineResult(engine="mock", ok=True, signals=[], metrics={})
        state = INVALIDATED if len(bars) <= 131 else CONFIRMED
        sigs = [Signal(
            engine="mock", kind="spring", direction="bull", state=state,
            formed_at=bars[90].date, formed_idx=90,
            confirmed_at=bars[100].date if state == CONFIRMED else None,
            confirmed_idx=100 if state == CONFIRMED else None,
            invalidated_at=bars[min(110, len(bars) - 1)].date if state == INVALIDATED else None,
            invalidated_idx=min(110, len(bars) - 1) if state == INVALIDATED else None,
            confirm_bars=10,
        )]
        return EngineResult(engine="mock", ok=True, signals=sigs, metrics={})

    bars = _mk_bars(160)
    rep = check_engine("mock", eng, bars, as_of_idx=130)
    assert not rep.passed, "D2 复现：invalidated->confirmed 重绘未被检出"


def test_all_engines_survive_truncated_data():
    """场景测试：截断/短数据下六引擎不得崩溃，体检降级不误判。"""
    from rdp.core.guard import check_engine_result, MIN_CUT_BARS
    short = BARS[: MIN_CUT_BARS - 20]
    for fn in ALL_ENGINES:
        rep, res = check_engine_result(fn.__module__.split(".")[-1], fn, short, len(short) - 1)
        assert rep is not None and res is not None  # 不抛异常即底线


def test_confluence_invalidated_event_votes_against():
    """场景测试：已失效事件必须投反向票(-1)，不得按原方向计票。"""
    from rdp.core.confluence import _timeliness
    from rdp.schema import Signal, CONFIRMED, BULL
    s = Signal(engine="pattern", kind="double_bottom", direction=BULL, state=CONFIRMED,
               formed_at="d", formed_idx=90, confirmed_at="d", confirmed_idx=95,
               confirm_bars=5, price=1.0, invalidated_idx=98, evidence={})
    _, v, _ = _timeliness([s], last_idx=100)
    assert v == -1, f"失效事件应投 -1，实得 {v}"
