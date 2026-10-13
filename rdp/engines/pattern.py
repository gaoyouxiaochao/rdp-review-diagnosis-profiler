# -*- coding: utf-8 -*-
"""引擎 4：形态识别 —— K 线形态子模块 + 结构形态子模块。

纪律：识别器先输出候选形态，再等突破/收盘确认。未完成的头肩顶、三角形
不得被当成已成立形态。候选与确认分开输出，状态可审计。
"""
from __future__ import annotations

from ..schema import Bar, EngineResult, Signal, CONFIRMED, CANDIDATE, BULL, BEAR, NEUTRAL
from ..core.indicators import swing_pivots

LEFT = 3
RIGHT = 3
MIN_BARS = 40
DOJI_RATIO = 0.1
# 双顶/双底两个摆动点之间的最小间隔：太近的是噪音不是形态（评审 P1-4）
MIN_GAP = 8
# 两顶/两底等高容差
LEVEL_TOL = 0.05


def _body(b: Bar) -> float:
    return abs(b.close - b.open)


def _candles(bars: list[Bar]) -> list[Signal]:
    out: list[Signal] = []
    for i in range(1, len(bars)):
        c, p = bars[i], bars[i - 1]
        rng = c.range_
        body = _body(c)
        lower = min(c.open, c.close) - c.low
        upper = c.high - max(c.open, c.close)

        if rng > 0 and body / rng <= DOJI_RATIO:
            out.append(Signal(
                engine="pattern", kind="doji", direction=NEUTRAL, state=CONFIRMED,
                formed_at=c.date, formed_idx=i, confirmed_at=c.date, confirmed_idx=i,
                confirm_bars=0, price=round(c.close, 3), strength=0.3,
                evidence={"body_range_ratio": round(body / rng, 3)},
            ))

        if rng > 0 and lower >= 2 * max(body, 1e-9) and upper <= body:
            out.append(Signal(
                engine="pattern", kind="hammer", direction=BULL, state=CONFIRMED,
                formed_at=c.date, formed_idx=i, confirmed_at=c.date, confirmed_idx=i,
                confirm_bars=0, price=round(c.close, 3), strength=0.55,
                evidence={"lower_shadow": round(lower, 3), "body": round(body, 3)},
            ))

        if c.close > c.open and p.close < p.open and c.close >= p.open and c.open <= p.close:
            out.append(Signal(
                engine="pattern", kind="bullish_engulfing", direction=BULL, state=CONFIRMED,
                formed_at=c.date, formed_idx=i, confirmed_at=c.date, confirmed_idx=i,
                confirm_bars=0, price=round(c.close, 3), strength=0.6,
                evidence={"prev_open": p.open, "prev_close": p.close, "open": c.open, "close": c.close},
            ))
        if c.close < c.open and p.close > p.open and c.close <= p.open and c.open >= p.close:
            out.append(Signal(
                engine="pattern", kind="bearish_engulfing", direction=BEAR, state=CONFIRMED,
                formed_at=c.date, formed_idx=i, confirmed_at=c.date, confirmed_idx=i,
                confirm_bars=0, price=round(c.close, 3), strength=0.6,
                evidence={"prev_open": p.open, "prev_close": p.close, "open": c.open, "close": c.close},
            ))
    return out


def _double_tops_bottoms(bars: list[Bar], pivots: list) -> list[Signal]:
    """双顶/双底：两个相近摆动点 + 中间反向点，突破颈线才确认。"""
    out: list[Signal] = []
    highs = [p for p in pivots if p.kind == "high"]
    lows = [p for p in pivots if p.kind == "low"]
    last = len(bars) - 1

    for a, b in zip(highs, highs[1:]):
        if b.confirmed_idx > last or b.idx - a.idx < MIN_GAP:
            continue
        mid = [p for p in lows if a.idx < p.idx < b.idx]
        if not mid:
            continue
        neck = min(p.price for p in mid)
        if abs(b.price - a.price) / max(a.price, 1e-9) > LEVEL_TOL:
            continue
        broken = any(bars[i].close < neck for i in range(b.confirmed_idx, last + 1))
        out.append(Signal(
            engine="pattern", kind="double_top",
            direction=BEAR,
            state=CONFIRMED if broken else CANDIDATE,
            formed_at=bars[b.idx].date, formed_idx=b.idx,
            confirmed_at=(bars[b.confirmed_idx].date if broken else None),
            confirmed_idx=(b.confirmed_idx if broken else None),
            confirm_bars=RIGHT, price=round(b.price, 3),
            strength=0.7 if broken else 0.4,
            evidence={"left_top": round(a.price, 3), "right_top": round(b.price, 3),
                      "neckline": round(neck, 3), "break_required": not broken},
        ))

    for a, b in zip(lows, lows[1:]):
        if b.confirmed_idx > last or b.idx - a.idx < MIN_GAP:
            continue
        mid = [p for p in highs if a.idx < p.idx < b.idx]
        if not mid:
            continue
        neck = max(p.price for p in mid)
        if abs(b.price - a.price) / max(a.price, 1e-9) > LEVEL_TOL:
            continue
        broken = any(bars[i].close > neck for i in range(b.confirmed_idx, last + 1))
        out.append(Signal(
            engine="pattern", kind="double_bottom",
            direction=BULL,
            state=CONFIRMED if broken else CANDIDATE,
            formed_at=bars[b.idx].date, formed_idx=b.idx,
            confirmed_at=(bars[b.confirmed_idx].date if broken else None),
            confirmed_idx=(b.confirmed_idx if broken else None),
            confirm_bars=RIGHT, price=round(b.price, 3),
            strength=0.7 if broken else 0.4,
            evidence={"left_bottom": round(a.price, 3), "right_bottom": round(b.price, 3),
                      "neckline": round(neck, 3), "break_required": not broken},
        ))
    return out


def run(bars: list[Bar]) -> EngineResult:
    if len(bars) < MIN_BARS:
        return EngineResult("pattern", False, error="数据不足", notes=["少于 %d 根K线" % MIN_BARS])

    pivots = swing_pivots([b.high for b in bars], [b.low for b in bars], LEFT, RIGHT)
    candles = _candles(bars)
    struct = _double_tops_bottoms(bars, pivots)
    confirmed = [s for s in struct if s.state == CONFIRMED]
    candidate = [s for s in struct if s.state == CANDIDATE]
    return EngineResult(
        "pattern", True, signals=candles + struct,
        metrics={
            "candle_signals": len(candles),
            "structure_confirmed": len(confirmed),
            "structure_candidate": len(candidate),
            "latest_candle": (f"{candles[-1].kind}@{candles[-1].formed_at}" if candles else "none"),
            "latest_structure": (f"{struct[-1].kind}/{struct[-1].state}@{struct[-1].formed_at}"
                                 if struct else "none"),
        },
        notes=["结构形态未破颈线只记 candidate，不构成已确认信号"],
    )
