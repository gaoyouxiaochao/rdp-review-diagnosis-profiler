# -*- coding: utf-8 -*-
"""引擎 1：成交量分布 Volume Profile / POC / VAH / VAL。

算法参考开源方案 mervinj3546/volume-profile 的规则（价格分箱 + 量归属 + POC + 价值区间），
此处为纯 Python 独立实现，未使用任何外部代码。

因果性：窗口为 [i-window+1, i] 的滚动区间，只使用已收盘数据，天然无未来函数。
"""
from __future__ import annotations

from ..schema import Bar, EngineResult, Signal, CONFIRMED, BULL, BEAR, NEUTRAL, SCOPE_STATE

WINDOW = 60
BINS = 24
VALUE_AREA_PCT = 0.70

MIN_BARS = 20


def _profile(bars: list[Bar]) -> dict:
    lo = min(b.low for b in bars)
    hi = max(b.high for b in bars)
    if hi <= lo:
        return {}
    width = (hi - lo) / BINS
    vol = [0.0] * BINS
    for b in bars:
        idx = min(BINS - 1, max(0, int((b.typical - lo) / width)))
        vol[idx] += b.volume
    total = sum(vol) or 1.0
    poc_i = max(range(BINS), key=lambda i: vol[i])
    poc = lo + (poc_i + 0.5) * width

    order = sorted(range(BINS), key=lambda i: vol[i], reverse=True)
    acc = 0.0
    chosen = []
    for i in order:
        chosen.append(i)
        acc += vol[i]
        if acc / total >= VALUE_AREA_PCT:
            break
    vah = lo + (max(chosen) + 1) * width
    val = lo + min(chosen) * width
    return {
        "poc": round(poc, 3),
        "vah": round(vah, 3),
        "val": round(val, 3),
        "low": round(lo, 3),
        "high": round(hi, 3),
        "poc_bin_volume_ratio": round(vol[poc_i] / total, 4),
    }


def run(bars: list[Bar]) -> EngineResult:
    if len(bars) < MIN_BARS:
        return EngineResult("volume_profile", False, error="数据不足", notes=["少于 %d 根K线" % MIN_BARS])

    win = bars[-WINDOW:]
    prof = _profile(win)
    if not prof:
        return EngineResult("volume_profile", False, error="价格区间退化")

    last = bars[-1]
    idx = len(bars) - 1
    poc, vah, val = prof["poc"], prof["vah"], prof["val"]
    span = max(vah - val, 1e-9)

    if last.close > vah:
        pos, direction, strength = "value_area_high_above", BULL, 0.8
    elif last.close < val:
        pos, direction, strength = "value_area_low_below", BEAR, 0.8
    elif last.close > poc:
        pos, direction, strength = "above_poc", BULL, 0.5
    elif last.close < poc:
        pos, direction, strength = "below_poc", BEAR, 0.5
    else:
        pos, direction, strength = "at_poc", NEUTRAL, 0.3

    dist = (last.close - poc) / span
    sig = Signal(
        engine="volume_profile",
        kind="vp_position",
        direction=direction,
        state=CONFIRMED,
        formed_at=last.date,
        formed_idx=idx,
        confirmed_at=last.date,
        confirmed_idx=idx,
        confirm_bars=0,
        price=round(last.close, 3),
        strength=strength,
        # 筹码位置是"截至最后一根K线"的状态量，不是历史事件，不参与 walk-forward 对拍
        scope=SCOPE_STATE,
        evidence={
            "window": WINDOW,
            "bins": BINS,
            "poc": poc,
            "vah": vah,
            "val": val,
            "close_vs_poc": "above" if last.close > poc else ("below" if last.close < poc else "at"),
            "poc_distance_in_value_area": round(dist, 3),
        },
    )

    prof["close"] = round(last.close, 3)
    prof["position"] = pos
    return EngineResult(
        "volume_profile", True,
        signals=[sig],
        metrics=prof,
        notes=["窗口 %d 根 / %d 箱 / 价值区间 70%%" % (WINDOW, BINS)],
    )
