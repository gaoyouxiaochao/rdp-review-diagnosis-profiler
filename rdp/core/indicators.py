# -*- coding: utf-8 -*-
"""纯 Python 技术指标。零外部依赖，不引入 TA-Lib（Windows 编译风险）。

硬约束：所有函数必须是因果的——第 i 个输出只允许使用 0..i 的数据。
需要右侧确认的形态（分形/摆动点）在末尾 confirm_bars 根输出 None。
"""
from __future__ import annotations

from dataclasses import dataclass


def sma(vals: list[float], n: int) -> list[float | None]:
    out: list[float | None] = []
    acc = 0.0
    for i, v in enumerate(vals):
        acc += v
        if i >= n:
            acc -= vals[i - n]
        out.append(acc / n if i >= n - 1 else None)
    return out


def ema(vals: list[float], n: int) -> list[float | None]:
    k = 2.0 / (n + 1.0)
    out: list[float | None] = []
    prev: float | None = None
    for i, v in enumerate(vals):
        if prev is None:
            if i < n - 1:
                out.append(None)
                continue
            prev = sum(vals[:n]) / n
            out.append(prev)
            continue
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(closes: list[float], n: int = 14) -> list[float | None]:
    if len(closes) < 2:
        return [None] * len(closes)
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = _wilder(gains, n)
    al = _wilder(losses, n)
    out: list[float | None] = []
    for g, l in zip(ag, al):
        if g is None or l is None:
            out.append(None)
        elif g + l == 0:
            out.append(50.0)
        else:
            out.append(100.0 * g / (g + l))
    return out


def _wilder(vals: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(vals)
    if len(vals) < n:
        return out
    prev = sum(vals[1:n + 1]) / n
    out[n] = prev
    for i in range(n + 1, len(vals)):
        prev = (prev * (n - 1) + vals[i]) / n
        out[i] = prev
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> list[float | None]:
    trs = [highs[0] - lows[0]] if closes else []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    return _wilder(trs, n)


@dataclass
class MacdOut:
    dif: list[float | None]
    dea: list[float | None]
    hist: list[float | None]


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MacdOut:
    ef = ema(closes, fast)
    es = ema(closes, slow)
    dif: list[float | None] = [
        (a - b) if (a is not None and b is not None) else None
        for a, b in zip(ef, es)
    ]
    known = [d for d in dif if d is not None]
    dea_all = ema(known, signal) if known else []
    offset = len(dif) - len(dea_all)
    dea: list[float | None] = [None] * offset + list(dea_all)
    hist: list[float | None] = [
        (a - b) if (a is not None and b is not None) else None
        for a, b in zip(dif, dea)
    ]
    return MacdOut(dif=dif, dea=dea, hist=hist)


@dataclass
class Pivot:
    idx: int
    kind: str          # "high" | "low"
    price: float
    confirmed_idx: int  # 确认发生在哪一根（idx + right）


def swing_pivots(highs: list[float], lows: list[float], left: int = 3, right: int = 3) -> list[Pivot]:
    """分形摆动点。第 i 个点需要 i+right 根收盘后才能确认——这就是 confirm_bars。"""
    pivots: list[Pivot] = []
    n = len(highs)
    for i in range(left, n - right):
        h, l = highs[i], lows[i]
        if all(h >= highs[j] for j in range(i - left, i + right + 1) if j != i):
            pivots.append(Pivot(i, "high", h, i + right))
        elif all(l <= lows[j] for j in range(i - left, i + right + 1) if j != i):
            pivots.append(Pivot(i, "low", l, i + right))
    return pivots


def volume_ma(volumes: list[float], n: int = 20) -> list[float | None]:
    return sma(volumes, n)


def pct_change(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return (a - b) / b * 100.0
