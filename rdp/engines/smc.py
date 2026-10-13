# -*- coding: utf-8 -*-
"""引擎 2：SMC 聪明钱结构 —— 摆动点 / BOS / CHoCH / 订单块 / FVG。

算法规则参考 joshyattridge/smart-money-concepts 公开定义，此处为纯 Python 独立实现。
关键纪律：摆动点需右侧确认（confirm_bars=3），未确认不得输出为已确认事件。
"""
from __future__ import annotations

from ..schema import Bar, EngineResult, Signal, CONFIRMED, CANDIDATE, BULL, BEAR
from ..core.indicators import swing_pivots

LEFT = 3
RIGHT = 3
MIN_BARS = 30


def _last_structure(bars: list[Bar], pivots: list) -> list[Signal]:
    """BOS / CHoCH：价格突破此前已确认的反向摆动点。"""
    out: list[Signal] = []
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]

    confirmed_highs = [p for p in pivots if p.kind == "high" and p.confirmed_idx < len(bars)]
    confirmed_lows = [p for p in pivots if p.kind == "low" and p.confirmed_idx < len(bars)]
    if not confirmed_highs or not confirmed_lows:
        return out

    trend = NEUTRAL_STATE
    for i in range(max(confirmed_highs[0].confirmed_idx, confirmed_lows[0].confirmed_idx), len(bars)):
        known_h = [p for p in confirmed_highs if p.confirmed_idx <= i]
        known_l = [p for p in confirmed_lows if p.confirmed_idx <= i]
        if not known_h or not known_l:
            continue
        hh = max(known_h, key=lambda p: p.idx)
        ll = max(known_l, key=lambda p: p.idx)
        if highs[i] > hh.price and trend != BULL:
            out.append(Signal(
                engine="smc", kind="bos" if trend == NEUTRAL_STATE else "choch",
                direction=BULL, state=CONFIRMED,
                formed_at=bars[i].date, formed_idx=i,
                confirmed_at=bars[i].date, confirmed_idx=i,
                confirm_bars=0, price=round(hh.price, 3),
                strength=0.7 if trend == NEUTRAL_STATE else 0.9,
                evidence={"broken_pivot_date": bars[hh.idx].date,
                          "broken_pivot_price": round(hh.price, 3),
                          "break_close": round(bars[i].close, 3),
                          "pivot_confirmed_at": bars[hh.confirmed_idx].date},
            ))
            trend = BULL
        elif lows[i] < ll.price and trend != BEAR:
            out.append(Signal(
                engine="smc", kind="bos" if trend == NEUTRAL_STATE else "choch",
                direction=BEAR, state=CONFIRMED,
                formed_at=bars[i].date, formed_idx=i,
                confirmed_at=bars[i].date, confirmed_idx=i,
                confirm_bars=0, price=round(ll.price, 3),
                strength=0.7 if trend == NEUTRAL_STATE else 0.9,
                evidence={"broken_pivot_date": bars[ll.idx].date,
                          "broken_pivot_price": round(ll.price, 3),
                          "break_close": round(bars[i].close, 3),
                          "pivot_confirmed_at": bars[ll.confirmed_idx].date},
            ))
            trend = BEAR
    return out


NEUTRAL_STATE = "neutral"


def _order_blocks(bars: list[Bar], signals: list[Signal]) -> list[Signal]:
    """订单块：突破前的**最后一根反向 K 线**区间。

    定义（SMC 通行口径）：向上突破（BULL）的订单块 = 突破发生前最近的一根阴线；
    向下突破（BEAR）= 最近一根阳线。

    评审修正（P0-1）：旧实现 while 条件写反——"只要 bars[j] 是反向就继续往前退"，
    退过所有反向 K 线后停在同向 K 线，取了一根同向 K 线当订单块，方向完全反了。
    正确做法是：从 i-1 向前扫描，遇到第一根反向 K 线即停，那根就是订单块。

    契约要点：订单块**位置**在第 j 根，但要等突破发生在第 i 根时它才被识别出来，
    所以 confirm_bars = i - j，confirmed_idx = i。若写成 0，等于宣称"第 j 根收盘
    就知道它是订单块"，walk-forward 对拍必然在截断端报错。
    """
    out: list[Signal] = []
    for s in signals:
        i = s.formed_idx
        # 反向 K 线的判定：BULL 突破找阴线（close<open），BEAR 突破找阳线（close>open）
        def is_opposite(j_: int) -> bool:
            return (bars[j_].close < bars[j_].open) if s.direction == BULL \
                else (bars[j_].close > bars[j_].open)

        j = i - 1
        while j >= 1 and not is_opposite(j):
            j -= 1
        if j < 1 or not is_opposite(j):
            continue
        lag = i - j
        out.append(Signal(
            engine="smc", kind="order_block", direction=s.direction,
            state=CONFIRMED, formed_at=bars[j].date, formed_idx=j,
            confirmed_at=bars[i].date, confirmed_idx=i, confirm_bars=lag,
            price=round((bars[j].high + bars[j].low) / 2, 3),
            strength=0.5,
            evidence={"ob_high": round(bars[j].high, 3), "ob_low": round(bars[j].low, 3),
                      "ob_bar": bars[j].date,
                      "ob_candle": "bearish" if s.direction == BULL else "bullish",
                      "identified_at": bars[i].date,
                      "identify_lag_bars": lag,
                      "linked_event": f"{s.kind}@{s.formed_at}"},
        ))
    return out


def _fvgs(bars: list[Bar]) -> list[Signal]:
    """公平价值缺口：三根 K 线之间的真空区。"""
    out: list[Signal] = []
    for i in range(2, len(bars)):
        if bars[i].low > bars[i - 2].high:
            out.append(Signal(
                engine="smc", kind="fvg", direction=BULL, state=CONFIRMED,
                formed_at=bars[i].date, formed_idx=i,
                confirmed_at=bars[i].date, confirmed_idx=i, confirm_bars=0,
                price=round((bars[i].low + bars[i - 2].high) / 2, 3),
                strength=0.4,
                evidence={"gap_low": round(bars[i - 2].high, 3), "gap_high": round(bars[i].low, 3)},
            ))
        elif bars[i].high < bars[i - 2].low:
            out.append(Signal(
                engine="smc", kind="fvg", direction=BEAR, state=CONFIRMED,
                formed_at=bars[i].date, formed_idx=i,
                confirmed_at=bars[i].date, confirmed_idx=i, confirm_bars=0,
                price=round((bars[i].high + bars[i - 2].low) / 2, 3),
                strength=0.4,
                evidence={"gap_low": round(bars[i].high, 3), "gap_high": round(bars[i - 2].low, 3)},
            ))
    return out


def run(bars: list[Bar]) -> EngineResult:
    if len(bars) < MIN_BARS:
        return EngineResult("smc", False, error="数据不足", notes=["少于 %d 根K线" % MIN_BARS])

    pivots = swing_pivots([b.high for b in bars], [b.low for b in bars], LEFT, RIGHT)
    struct = _last_structure(bars, pivots)
    obs = _order_blocks(bars, struct)
    fvgs = _fvgs(bars)

    pending = [p for p in pivots if p.confirmed_idx >= len(bars)]
    signals = struct + obs + fvgs
    trend = struct[-1].direction if struct else "unknown"
    return EngineResult(
        "smc", True, signals=signals,
        metrics={
            "pivot_count": len(pivots),
            "pending_pivots": len(pending),
            "structure_events": len(struct),
            "order_blocks": len(obs),
            "fvg_count": len(fvgs),
            "structure_trend": trend,
            "last_structure": (f"{struct[-1].kind}/{struct[-1].direction}@{struct[-1].formed_at}"
                               if struct else "none"),
        },
        notes=["摆动点 left=%d right=%d，右侧确认后事件才成立" % (LEFT, RIGHT)],
    )
