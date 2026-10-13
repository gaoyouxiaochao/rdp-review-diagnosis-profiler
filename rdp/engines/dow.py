# -*- coding: utf-8 -*-
"""引擎 6：道氏理论趋势结构 —— 高点/低点序列、次级折返、量能确认。

借鉴的开源能力（Dow Theory 类项目）：
    - 主要趋势判定：依次抬高的高点 + 依次抬高的低点 = 上升趋势，反之为下降
    - 次级折返：逆向运动通常回吐前一段的 1/3 ~ 2/3，超出 2/3 需警惕趋势反转
    - 量能确认：主要趋势方向上成交量应当配合放大
改写说明：开源实现多为 Pine Script，依赖 ta.pivothigh/ta.pivotlow 的脚本语义；
这里改用自研 swing_pivots（left/right 对称分形），确认延迟显式写成 confirm_bars。

因果纪律：
    - 摆动点需右侧 right 根确认，序列信号在确认根才成立；
    - **每一组相邻摆动点都出一条信号**（不是只出"最新一条"），否则 walk-forward
      对拍时截断端会凭空多出/少掉信号，闸门必然误报。
"""
from __future__ import annotations

from ..schema import (
    Bar, EngineResult, Signal,
    CONFIRMED, CANDIDATE, BULL, BEAR, NEUTRAL, SCOPE_STATE,
)
from ..core.indicators import swing_pivots

LEFT = 3
RIGHT = 3
MIN_BARS = 45
VOL_WINDOW = 30


def _sequence_signals(bars: list[Bar], pivots: list) -> list[Signal]:
    """相邻同类摆动点的序列关系：抬高/降低。"""
    out: list[Signal] = []
    last = len(bars) - 1
    for kind, up_kind, down_kind in (("high", "dow_higher_high", "dow_lower_high"),
                                     ("low", "dow_higher_low", "dow_lower_low")):
        ps = [p for p in pivots if p.kind == kind]
        for a, b in zip(ps, ps[1:]):
            if b.confirmed_idx > last:
                continue
            rising = b.price > a.price
            falling = b.price < a.price
            if not (rising or falling):
                continue
            out.append(Signal(
                engine="dow",
                kind=(up_kind if rising else down_kind),
                direction=(BULL if rising else BEAR),
                state=CONFIRMED,
                formed_at=bars[b.idx].date, formed_idx=b.idx,
                confirmed_at=bars[b.confirmed_idx].date, confirmed_idx=b.confirmed_idx,
                confirm_bars=RIGHT,
                price=round(b.price, 3),
                strength=0.6,
                evidence={
                    "prev_pivot_date": bars[a.idx].date,
                    "prev_pivot_price": round(a.price, 3),
                    "curr_pivot_date": bars[b.idx].date,
                    "curr_pivot_price": round(b.price, 3),
                    "delta_pct": round((b.price - a.price) / max(a.price, 1e-9) * 100, 2),
                    "pivot_kind": kind,
                    "confirm_rule": f"left={LEFT},right={RIGHT}",
                },
            ))
    out.sort(key=lambda s: s.formed_idx)
    return out


def _retracement(bars: list[Bar], pivots: list) -> dict:
    """最近一段主升/主跌被回吐的比例。"""
    hs = [p for p in pivots if p.kind == "high"]
    ls = [p for p in pivots if p.kind == "low"]
    if len(hs) < 2 or len(ls) < 2:
        return {}
    h0, h1 = hs[-2], hs[-1]
    l0, l1 = ls[-2], ls[-1]
    last_close = bars[-1].close
    # 取时间上更晚的那一段作为"当前主段"
    if h1.idx >= l1.idx:
        seg_hi, seg_lo = h1.price, l1.price
        span = seg_hi - seg_lo
        retr = (seg_hi - last_close) / span if span > 0 else 0.0
        seg = "down"
    else:
        seg_lo, seg_hi = l1.price, h1.price
        span = seg_hi - seg_lo
        retr = (last_close - seg_lo) / span if span > 0 else 0.0
        seg = "up"
    return {
        "segment": seg,
        "segment_high": round(seg_hi, 3),
        "segment_low": round(seg_lo, 3),
        # 价格已越过前一段边界时比例会超出 0~1，截断到 [-1, 2] 避免显示失真
        "retracement_pct": round(max(-1.0, min(2.0, retr)) * 100, 2),
        "beyond_two_thirds": bool(retr > 2.0 / 3.0),
        "beyond_segment": bool(retr < 0.0 or retr > 1.0),
    }


def _volume_confirm(bars: list[Bar]) -> dict:
    win = bars[-VOL_WINDOW:]
    up_v = sum(b.volume for b in win if b.close > b.open)
    dn_v = sum(b.volume for b in win if b.close < b.open)
    tot = up_v + dn_v
    return {
        "window": VOL_WINDOW,
        "up_volume_ratio": round(up_v / tot, 3) if tot else 0.0,
        "volume_bias": ("up" if up_v > dn_v else ("down" if dn_v > up_v else "flat")),
    }


def run(bars: list[Bar]) -> EngineResult:
    if len(bars) < MIN_BARS:
        return EngineResult("dow", False, error="数据不足",
                            notes=["少于 %d 根K线" % MIN_BARS])

    pivots = swing_pivots([b.high for b in bars], [b.low for b in bars], LEFT, RIGHT)
    seq = _sequence_signals(bars, pivots)

    hs = [p for p in pivots if p.kind == "high"]
    ls = [p for p in pivots if p.kind == "low"]
    hh = len(hs) >= 2 and hs[-1].price > hs[-2].price
    lh = len(hs) >= 2 and hs[-1].price < hs[-2].price
    hl = len(ls) >= 2 and ls[-1].price > ls[-2].price
    ll = len(ls) >= 2 and ls[-1].price < ls[-2].price

    if hh and hl:
        phase, direction = "uptrend", BULL
    elif lh and ll:
        phase, direction = "downtrend", BEAR
    else:
        phase, direction = "sideways", NEUTRAL

    retr = _retracement(bars, pivots)
    vc = _volume_confirm(bars)
    confirmed = [s for s in seq if s.state == CONFIRMED]
    cand = [s for s in seq if s.state == CANDIDATE]

    phase_sig = Signal(
        engine="dow", kind="dow_phase", direction=direction, state=CONFIRMED,
        formed_at=bars[-1].date, formed_idx=len(bars) - 1,
        confirmed_at=bars[-1].date, confirmed_idx=len(bars) - 1,
        confirm_bars=0, price=round(bars[-1].close, 3),
        strength=(0.8 if phase != "sideways" else 0.3),
        scope=SCOPE_STATE,
        evidence={"phase": phase, "higher_high": bool(hh), "higher_low": bool(hl),
                  "lower_high": bool(lh), "lower_low": bool(ll),
                  "retracement": retr, "volume_confirm": vc},
    )

    return EngineResult(
        "dow", True, signals=seq + [phase_sig],
        metrics={
            "phase": phase,
            "pivot_count": len(pivots),
            "sequence_signals": len(seq),
            "confirmed_sequences": len(confirmed),
            "candidate_sequences": len(cand),
            "higher_high": bool(hh),
            "higher_low": bool(hl),
            "lower_high": bool(lh),
            "lower_low": bool(ll),
            "retracement": retr,
            "volume_confirm": vc,
        },
        notes=["摆动点 left=%d right=%d；序列信号在确认根成立" % (LEFT, RIGHT)],
    )
