# -*- coding: utf-8 -*-
"""引擎 5：Wyckoff 量价结构 —— 交易区间 / Spring / Upthrust / Effort vs Result。

借鉴的开源能力（Wyckoff 方法类项目，Pine/Python 均有成熟实现）：
    - 交易区间（Trading Range）与吸筹/派发的划分
    - Spring / Upthrust（UT）两类"假突破后收回"事件
    - Effort vs Result：放量却推不出幅度，视为吸收/派发的蛛丝马迹
改写说明：开源实现多为 Pine Script 且大量使用 barstate.isconfirmed 之类
的脚本运行时语义，这里全部改为纯 Python 的滚动窗口 + 延迟确认，并把"区间边界"
严格定义为"截止 i-1 的窗口"，杜绝把第 i 根自身算进边界。

因果纪律：
    - 区间上下沿只取 [i-TR_WINDOW, i-1]，不含第 i 根；
    - Spring/Upthrust 先记 candidate，需后续 CONFIRM_BARS 根不创新低/新高才转
      confirmed，与 M1 三态机一致。
"""
from __future__ import annotations

from ..schema import (
    Bar, EngineResult, Signal,
    CONFIRMED, CANDIDATE, BULL, BEAR, NEUTRAL, SCOPE_STATE,
)
from ..core.indicators import volume_ma

TR_WINDOW = 50
RANGE_WIDTH_PCT = 0.28      # 区间振幅 / 下沿 小于此值判为"交易区间"
CONFIRM_BARS = 2            # Spring/Upthrust 的延迟确认根数
VOL_SURGE = 1.8             # 放量阈值（相对 20 日均量）
MIN_BARS = 60


def _range_of(bars: list[Bar], i: int) -> tuple[float, float, float]:
    """截至 i-1 的滚动交易区间（不含第 i 根）。"""
    lo_b = max(0, i - TR_WINDOW)
    win = bars[lo_b:i]
    if not win:
        return 0.0, 0.0, 0.0
    hi = max(b.high for b in win)
    lo = min(b.low for b in win)
    return hi, lo, (hi - lo) / max(lo, 1e-9)


def _spring_upthrust(bars: list[Bar]) -> list[Signal]:
    out: list[Signal] = []
    n = len(bars)
    for i in range(TR_WINDOW, n):
        hi, lo, width = _range_of(bars, i)
        if width == 0 or width > RANGE_WIDTH_PCT:
            continue
        b = bars[i]

        # Spring：跌破下沿后收盘收回区间内
        if b.low < lo and b.close > lo:
            ci = i + CONFIRM_BARS
            ok = ci < n and all(bars[k].close > lo for k in range(i, ci + 1))
            out.append(Signal(
                engine="wyckoff", kind="spring", direction=BULL,
                state=CONFIRMED if ok else CANDIDATE,
                formed_at=b.date, formed_idx=i,
                confirmed_at=(bars[ci].date if ok else None),
                confirmed_idx=(ci if ok else None),
                confirm_bars=CONFIRM_BARS,
                price=round(lo, 3), strength=0.75,
                evidence={"range_low": round(lo, 3), "range_high": round(hi, 3),
                          "pierce_low": round(b.low, 3), "reclaim_close": round(b.close, 3),
                          "range_width_pct": round(width, 4),
                          "window": TR_WINDOW},
            ))
            continue

        # Upthrust：突破上沿后收盘跌回区间内
        if b.high > hi and b.close < hi:
            ci = i + CONFIRM_BARS
            ok = ci < n and all(bars[k].close < hi for k in range(i, ci + 1))
            out.append(Signal(
                engine="wyckoff", kind="upthrust", direction=BEAR,
                state=CONFIRMED if ok else CANDIDATE,
                formed_at=b.date, formed_idx=i,
                confirmed_at=(bars[ci].date if ok else None),
                confirmed_idx=(ci if ok else None),
                confirm_bars=CONFIRM_BARS,
                price=round(hi, 3), strength=0.75,
                evidence={"range_low": round(lo, 3), "range_high": round(hi, 3),
                          "pierce_high": round(b.high, 3), "fallback_close": round(b.close, 3),
                          "range_width_pct": round(width, 4),
                          "window": TR_WINDOW},
            ))
    return out


def _effort_result(bars: list[Bar]) -> list[Signal]:
    """Effort vs Result：放量却没走出幅度 => 有人在吸收/派发。"""
    out: list[Signal] = []
    if len(bars) < 25:
        return out
    vma = volume_ma([b.volume for b in bars], 20)
    for i in range(21, len(bars)):
        v = vma[i]
        if not v:
            continue
        b = bars[i]
        rng_pct = b.range_ / max(bars[i - 1].close, 1e-9)
        if b.volume < v * VOL_SURGE:
            continue
        if rng_pct > 0.025:
            continue  # 放量且走出幅度，属正常推进，不构成异常
        hi, lo, width = _range_of(bars, i)
        if width == 0:
            continue
        pos = (b.close - lo) / max(hi - lo, 1e-9)
        direction = BULL if pos < 0.35 else (BEAR if pos > 0.65 else NEUTRAL)
        kind = "effort_no_result_low" if pos < 0.35 else (
            "effort_no_result_high" if pos > 0.65 else "effort_no_result_mid")
        out.append(Signal(
            engine="wyckoff", kind=kind, direction=direction, state=CONFIRMED,
            formed_at=b.date, formed_idx=i,
            confirmed_at=b.date, confirmed_idx=i, confirm_bars=0,
            price=round(b.close, 3), strength=0.45,
            evidence={"volume": round(b.volume, 0), "vol_ma20": round(v, 0),
                      "vol_surge_x": round(b.volume / v, 2),
                      "range_pct": round(rng_pct, 4),
                      "position_in_range": round(pos, 3)},
        ))
    return out


def run(bars: list[Bar]) -> EngineResult:
    if len(bars) < MIN_BARS:
        return EngineResult("wyckoff", False, error="数据不足",
                            notes=["少于 %d 根K线" % MIN_BARS])

    springs = _spring_upthrust(bars)
    efforts = _effort_result(bars)

    hi, lo, width = _range_of(bars, len(bars))
    last = bars[-1]
    in_range = 0 < width <= RANGE_WIDTH_PCT
    pos = (last.close - lo) / max(hi - lo, 1e-9) if hi > lo else 0.5

    if in_range:
        # 区间内，用近端方向定性：偏底部=吸筹，偏顶部=派发
        phase = "accumulation" if pos < 0.4 else ("distribution" if pos > 0.6 else "trading_range")
    else:
        win = bars[-TR_WINDOW:]
        up = win[-1].close > win[0].close
        phase = "markup" if up else "markdown"

    phase_sig = Signal(
        engine="wyckoff", kind="wyckoff_phase",
        direction=(BULL if phase in ("accumulation", "markup")
                   else (BEAR if phase in ("distribution", "markdown") else NEUTRAL)),
        state=CONFIRMED,
        formed_at=last.date, formed_idx=len(bars) - 1,
        confirmed_at=last.date, confirmed_idx=len(bars) - 1,
        confirm_bars=0, price=round(last.close, 3), strength=0.5,
        scope=SCOPE_STATE,
        evidence={"phase": phase, "range_high": round(hi, 3), "range_low": round(lo, 3),
                  "range_width_pct": round(width, 4),
                  "position_in_range": round(pos, 3), "window": TR_WINDOW},
    )

    signals = springs + efforts + [phase_sig]
    confirmed = sum(1 for s in springs if s.state == CONFIRMED)
    return EngineResult(
        "wyckoff", True, signals=signals,
        metrics={
            "phase": phase,
            "in_trading_range": bool(in_range),
            "range_high": round(hi, 3),
            "range_low": round(lo, 3),
            "range_width_pct": round(width, 4),
            "spring_count": sum(1 for s in springs if s.kind == "spring"),
            "upthrust_count": sum(1 for s in springs if s.kind == "upthrust"),
            "confirmed_break_events": confirmed,
            "candidate_break_events": len(springs) - confirmed,
            "effort_no_result_count": len(efforts),
        },
        notes=["区间边界取截至 i-1 的 %d 根窗口；假突破事件延迟 %d 根确认"
               % (TR_WINDOW, CONFIRM_BARS)],
    )
