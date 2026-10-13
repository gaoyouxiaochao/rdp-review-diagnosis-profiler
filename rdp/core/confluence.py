# -*- coding: utf-8 -*-
"""共振投票引擎（机制 M4）。

四类状态各自独立计票，杜绝"多个相关指标重复计票"：
    - 趋势方向   只取均线/收盘位置一路证据
    - 结构状态   只取 SMC 一路证据
    - 量价状态   只取成交量 + 背离一路证据
    - 时效状态   只取信号确认/失效时间戳一路证据
同一根 K 线、同一类证据只投一票，相关指标不叠加。
"""
from __future__ import annotations

from ..schema import (
    Bar, EngineResult, ConfluenceState, Signal,
    BULL, BEAR, NEUTRAL, CONFIRMED, INVALIDATED, SCOPE_EVENT,
    CONF_BULL, CONF_BEAR, CONF_DIVERGE, CONF_NONE,
)
from ..core.indicators import sma

MA_FAST = 20
MA_SLOW = 60
FRESH_BARS = 10


def _trend(bars: list[Bar]) -> tuple[str, int, dict]:
    closes = [b.close for b in bars]
    f = sma(closes, MA_FAST)
    s = sma(closes, MA_SLOW)
    if f[-1] is None or s[-1] is None:
        return NEUTRAL, 0, {"reason": "均线数据不足"}
    last = closes[-1]
    ev = {"ma20": round(f[-1], 3), "ma60": round(s[-1], 3), "close": round(last, 3)}
    if last > f[-1] and f[-1] > s[-1]:
        return BULL, 1, ev
    if last < f[-1] and f[-1] < s[-1]:
        return BEAR, -1, ev
    return NEUTRAL, 0, ev


def _structure(res: EngineResult | None) -> tuple[str, int, dict]:
    if not res or not res.ok:
        return "unknown", 0, {"reason": "SMC 引擎不可用"}
    struct = [s for s in res.signals if s.kind in ("bos", "choch")]
    if not struct:
        return "unknown", 0, {"reason": "无结构事件"}
    s = struct[-1]
    if s.direction == BULL and s.state == CONFIRMED:
        return "breakout_confirmed", 1, {"event": f"{s.kind}/{s.direction}@{s.formed_at}"}
    if s.direction == BEAR and s.state == CONFIRMED:
        return "breakdown_confirmed", -1, {"event": f"{s.kind}/{s.direction}@{s.formed_at}"}
    return "unconfirmed", 0, {"event": f"{s.kind}/{s.direction}@{s.formed_at}"}


def _volume_price(bars: list[Bar], div: EngineResult | None) -> tuple[str, int, dict]:
    if len(bars) < 21:
        return "unknown", 0, {"reason": "数据不足"}
    vols = [b.volume for b in bars]
    ma20 = sum(vols[-21:-1]) / 20.0
    cur = vols[-1]
    up = cur > ma20 * 1.2
    down = cur < ma20 * 0.8
    chg = bars[-1].close - bars[-2].close

    if div and div.ok:
        sigs = [s for s in div.signals if s.state == CONFIRMED and "hidden" not in s.kind]
        if sigs:
            s = sigs[-1]
            tag = "bull_divergence" if s.direction == BULL else "bear_divergence"
            return tag, (1 if s.direction == BULL else -1), {
                "event": f"{s.kind}@{s.formed_at}", "rsi": s.evidence.get("curr_rsi")}
    if up and chg > 0:
        return "volume_up_price_up", 1, {"vol_ma20": round(ma20, 0), "vol": round(cur, 0)}
    if up and chg < 0:
        return "volume_up_price_down", -1, {"vol_ma20": round(ma20, 0), "vol": round(cur, 0)}
    if down:
        return "volume_shrink", 0, {"vol_ma20": round(ma20, 0), "vol": round(cur, 0)}
    return "normal", 0, {"vol_ma20": round(ma20, 0), "vol": round(cur, 0)}


def _timeliness(all_signals: list[Signal], last_idx: int) -> tuple[str, int, dict]:
    """时效维度：最近一条**非结构类** confirmed 事件的新鲜度。

    评审修正（P0-2）：旧实现 `s.confirmed_idx >= len(all_signals) * 0` 中 `*0` 恒为 0，
    条件恒真，导致只要历史上有任何一条 confirmed 信号就恒投 +1 票 —— 全池共振分
    被系统性抬高。正确语义：只有"最近、且还没过时"的事件才配投时效票。

    规则：
    - 只统计 event 信号，且排除 smc 的 bos/choch（结构维度已计票，防止同源重复计票）；
    - 取 confirmed_idx 最大的一条，距今 <= FRESH_BARS 根投其方向票，否则 0 票；
    - 该最近事件若已被标记失效，投 -1。
    """
    cand = [s for s in all_signals
            if s.state == CONFIRMED and s.confirmed_idx is not None
            and s.scope == SCOPE_EVENT
            and not (s.engine == "smc" and s.kind in ("bos", "choch"))]
    if not cand:
        return "no_recent_event", 0, {"reason": "无可计时效的事件"}

    s = max(cand, key=lambda x: x.confirmed_idx)
    age = last_idx - s.confirmed_idx
    ev = {"latest_event": f"{s.engine}/{s.kind}@{s.confirmed_at}",
          "age_bars": age, "fresh_window": FRESH_BARS}

    if s.invalidated_idx is not None:
        return "recent_invalidated", -1, ev
    if age > FRESH_BARS:
        return "stale", 0, ev
    if s.direction == BULL:
        return "fresh_bull", 1, ev
    if s.direction == BEAR:
        return "fresh_bear", -1, ev
    return "fresh_neutral", 0, ev


def evaluate(bars: list[Bar], engines: dict[str, EngineResult]) -> ConfluenceState:
    votes: list[dict] = []

    t, tv, tev = _trend(bars)
    votes.append({"dimension": "trend", "value": t, "vote": tv, "evidence": tev})

    s, sv, sev = _structure(engines.get("smc"))
    votes.append({"dimension": "structure", "value": s, "vote": sv, "evidence": sev})

    v, vv, vev = _volume_price(bars, engines.get("divergence"))
    votes.append({"dimension": "volume_price", "value": v, "vote": vv, "evidence": vev})

    all_sig = [x for r in engines.values() for x in r.signals]
    tl, tlv, tlev = _timeliness(all_sig, len(bars) - 1)
    votes.append({"dimension": "timeliness", "value": tl, "vote": tlv, "evidence": tlev})

    score = sum(x["vote"] for x in votes)
    bull_votes = sum(1 for x in votes if x["vote"] > 0)
    bear_votes = sum(1 for x in votes if x["vote"] < 0)

    if score >= 2 and bull_votes >= 2:
        concl = CONF_BULL
    elif score <= -2 and bear_votes >= 2:
        concl = CONF_BEAR
    elif bull_votes >= 1 and bear_votes >= 1:
        concl = CONF_DIVERGE
    else:
        concl = CONF_NONE

    return ConfluenceState(
        trend=t, structure=s, volume_price=v, timeliness=tl,
        conclusion=concl, score=score, votes=votes,
    )
