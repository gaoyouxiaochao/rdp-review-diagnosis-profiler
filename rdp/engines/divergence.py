# -*- coding: utf-8 -*-
"""引擎 3：背离面板 —— 顶背离 / 底背离 / 隐藏背离。

输出严格区分"已形成"与"已确认"：
    第二个摆动点必须完成右侧确认（confirm_bars=3）后，背离才算 confirmed。
禁止用后来才出现的摆动点提前发出历史信号。
"""
from __future__ import annotations

from ..schema import Bar, EngineResult, Signal, CONFIRMED, CANDIDATE, BULL, BEAR
from ..core.indicators import swing_pivots, rsi

LEFT = 3
RIGHT = 3
RSI_N = 14
MIN_BARS = 40


def run(bars: list[Bar]) -> EngineResult:
    if len(bars) < MIN_BARS:
        return EngineResult("divergence", False, error="数据不足", notes=["少于 %d 根K线" % MIN_BARS])

    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    r = rsi(closes, RSI_N)
    pivots = swing_pivots(highs, lows, LEFT, RIGHT)

    signals: list[Signal] = []
    for kind, direction in (("high", BEAR), ("low", BULL)):
        ps = [p for p in pivots if p.kind == kind]
        for a, b in zip(ps, ps[1:]):
            ra, rb = r[a.idx], r[b.idx]
            if ra is None or rb is None:
                continue
            last_idx = len(bars) - 1
            confirmed_idx = b.confirmed_idx
            state = CONFIRMED if confirmed_idx <= last_idx else CANDIDATE
            conf_at = bars[confirmed_idx].date if confirmed_idx <= last_idx else None

            if kind == "high":
                higher_high = b.price > a.price
                lower_rsi = rb < ra
                if higher_high and lower_rsi:
                    signals.append(_mk("bear_divergence", BEAR, a, b, ra, rb, bars,
                                       state, conf_at, confirmed_idx, 0.75))
                elif b.price < a.price and rb > ra:
                    signals.append(_mk("hidden_bear_divergence", BEAR, a, b, ra, rb, bars,
                                       state, conf_at, confirmed_idx, 0.5))
            else:
                lower_low = b.price < a.price
                higher_rsi = rb > ra
                if lower_low and higher_rsi:
                    signals.append(_mk("bull_divergence", BULL, a, b, ra, rb, bars,
                                       state, conf_at, confirmed_idx, 0.75))
                elif b.price > a.price and rb < ra:
                    signals.append(_mk("hidden_bull_divergence", BULL, a, b, ra, rb, bars,
                                       state, conf_at, confirmed_idx, 0.5))

    signals.sort(key=lambda s: s.formed_idx)
    latest = signals[-1] if signals else None
    return EngineResult(
        "divergence", True, signals=signals,
        metrics={
            "rsi_period": RSI_N,
            "pivot_count": len(pivots),
            "total_divergences": len(signals),
            "latest": (f"{latest.kind}/{latest.direction}@{latest.formed_at}" if latest else "none"),
            "latest_state": (latest.state if latest else "none"),
            "rsi_last": (round(r[-1], 2) if r[-1] is not None else None),
        },
        notes=["摆动点 right=%d 确认后才计为 confirmed" % RIGHT],
    )


def _mk(kind, direction, a, b, ra, rb, bars, state, conf_at, conf_idx, strength) -> Signal:
    return Signal(
        engine="divergence", kind=kind, direction=direction, state=state,
        formed_at=bars[b.idx].date, formed_idx=b.idx,
        confirmed_at=conf_at, confirmed_idx=conf_idx if state == CONFIRMED else None,
        confirm_bars=RIGHT,
        price=round(b.price, 3), strength=strength,
        evidence={
            "prev_pivot_date": bars[a.idx].date,
            "prev_pivot_price": round(a.price, 3),
            "prev_rsi": round(ra, 2),
            "curr_pivot_date": bars[b.idx].date,
            "curr_pivot_price": round(b.price, 3),
            "curr_rsi": round(rb, 2),
            "pivot_confirm_rule": f"left={LEFT},right={RIGHT}",
        },
    )
