# -*- coding: utf-8 -*-
"""统一行情层。全模块唯一的行情入口——任何引擎禁止自己读文件。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..schema import Bar

KLINE_DIR = Path(__file__).resolve().parents[2] / "data" / "klines"

# 相邻两根 K 线的自然日期间隔超过该值记为"长缺口"（长假/停牌）
GAP_DAYS = 10
# long_gaps 最多保留多少条，防止异常数据把报告撑爆
GAP_KEEP = 8
DATE_FMT = "%Y-%m-%d"


class DataMissing(RuntimeError):
    pass


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, DATE_FMT)


def load_bars(code: str) -> tuple[dict, list[Bar]]:
    """返回 (meta, bars)。bars 保证按日期升序、日期唯一、OHLC 关系合法。"""
    p = KLINE_DIR / f"{code}.json"
    if not p.exists():
        raise DataMissing(f"no kline file for {code}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    seen: set[str] = set()
    bars: list[Bar] = []
    for b in raw.get("bars", []):
        d = b["date"]
        if d in seen:  # 上游偶发重复日期，保留先到的
            continue
        seen.add(d)
        bars.append(Bar(
            date=d,
            open=float(b["open"]),
            high=float(b["high"]),
            low=float(b["low"]),
            close=float(b["close"]),
            volume=float(b.get("volume") or 0.0),
            amount=float(b.get("amount") or 0.0),
        ))
    bars.sort(key=lambda x: x.date)
    return raw, bars


def available_codes() -> list[str]:
    if not KLINE_DIR.exists():
        return []
    return sorted(p.stem for p in KLINE_DIR.glob("*.json"))


def data_quality(bars: list[Bar]) -> dict:
    """A 股适配性体检：停牌、一字板、零成交、复权异常。

    评审修正：
    - P1-1：缺口用真实自然日差（datetime），旧实现"月差×31+日差"跨年算错；
    - P1-2：`limit_like` 旧条件 `range_>0 and high==low` 永假（high==low 时 range_=0），
      一字板定义为 high==low 且有成交（无量一字归停牌/零成交）。
    """
    if not bars:
        return {"ok": False, "reason": "empty"}
    zero_vol = sum(1 for b in bars if b.volume <= 0)
    zero_range = sum(1 for b in bars if b.range_ <= 0)
    limit_like = sum(1 for b in bars if b.high == b.low and b.volume > 0)
    bad = sum(1 for b in bars if b.close <= 0 or b.high < b.low)
    gaps: list[str] = []
    for i in range(1, len(bars)):
        try:
            delta = (_parse_date(bars[i].date) - _parse_date(bars[i - 1].date)).days
        except ValueError:
            continue
        if delta > GAP_DAYS:
            gaps.append(f"{bars[i - 1].date}->{bars[i].date}")
    return {
        "ok": bad == 0,
        "bars": len(bars),
        "zero_volume_days": zero_vol,
        "zero_range_days": zero_range,
        "limit_like_days": limit_like,
        "bad_bars": bad,
        "long_gaps": gaps[:GAP_KEEP],
        "long_gaps_total": len(gaps),
        "start": bars[0].date,
        "end": bars[-1].date,
    }
