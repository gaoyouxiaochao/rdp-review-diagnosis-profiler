# -*- coding: utf-8 -*-
"""画像流水线编排：行情 -> 4 引擎 -> 防未来函数体检 -> 共振 -> 评分 -> 画像。"""
from __future__ import annotations

from ..schema import Bar, Profile
from .loader import load_bars, data_quality
from .guard import check_engine_result
from .confluence import evaluate as confluence_evaluate
from .scorecard import evaluate as scorecard_evaluate, verdict_of
from ..engines import volume_profile, smc, divergence, pattern, wyckoff, dow

ENGINE_FNS = {
    "volume_profile": volume_profile.run,
    "smc": smc.run,
    "divergence": divergence.run,
    "pattern": pattern.run,
    "wyckoff": wyckoff.run,
    "dow": dow.run,
}

AS_OF = "2026-10-13"


def _as_of_idx(bars: list[Bar], as_of: str | None) -> int:
    if not as_of:
        return len(bars) - 1
    for i in range(len(bars) - 1, -1, -1):
        if bars[i].date <= as_of:
            return i
    return len(bars) - 1


def build(code: str, name: str = "", industry: str = "", as_of: str | None = AS_OF) -> Profile:
    meta, bars_all = load_bars(code)
    name = name or meta.get("name", "")
    idx = _as_of_idx(bars_all, as_of)
    bars = bars_all[: idx + 1]

    quality = data_quality(bars)
    engines: dict = {}
    guards: dict = {}
    for en, fn in ENGINE_FNS.items():
        # 体检必须用**未截断**的 bars_all：先截断再体检会让 walk-forward 退化成空转
        rep, res = check_engine_result(en, fn, bars_all, idx)
        guards[en] = rep
        engines[en] = res

    conf = confluence_evaluate(bars, engines)
    signals = [s for r in engines.values() for s in r.signals]
    card = scorecard_evaluate(engines, guards, quality, signals)

    p = Profile(
        code=code, name=name, industry=industry,
        as_of=bars[-1].date if bars else (as_of or ""),
        bar_count=len(bars),
        data_start=bars[0].date if bars else "",
        data_end=bars[-1].date if bars else "",
        close=round(bars[-1].close, 3) if bars else 0.0,
        engines=engines, guard=guards, confluence=conf, scorecard=card,
        data_quality=quality,
    )
    p.verdict, p.risks = verdict_of(p)
    return p


def build_all(targets: list[dict], as_of: str | None = AS_OF) -> tuple[list[Profile], list[dict]]:
    profiles: list[Profile] = []
    failed: list[dict] = []
    for t in targets:
        try:
            profiles.append(build(t["code"], t.get("name", ""), t.get("industry", ""), as_of))
        except Exception as e:  # 单票失败不影响全池
            failed.append({"code": t.get("code"), "name": t.get("name"), "error": str(e)})
    return profiles, failed
