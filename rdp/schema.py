# -*- coding: utf-8 -*-
"""统一数据契约。所有引擎与报告层只认这里的类型，禁止各层自造数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# 信号三态：候选 -> 确认 -> 失效（机制 M1）
CANDIDATE = "candidate"
CONFIRMED = "confirmed"
INVALIDATED = "invalidated"

# 方向
BULL = "bull"
BEAR = "bear"
NEUTRAL = "neutral"

# 信号作用域：
#   event —— 历史事件，形成于某一根具体的 K 线，可被 walk-forward 对拍
#   state —— 当前状态量，天然依附于"最后一根K线"，不参与对拍（否则必误报）
SCOPE_EVENT = "event"
SCOPE_STATE = "state"

# 状态推进的单调序：candidate -> confirmed/invalidated 只允许单向前进
STATE_RANK = {CANDIDATE: 0, CONFIRMED: 1, INVALIDATED: 1}

# 共振结论
CONF_BULL = "bull_confluence"
CONF_BEAR = "bear_confluence"
CONF_DIVERGE = "divergence"
CONF_NONE = "no_confluence"


@dataclass
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0

    @property
    def typical(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def range_(self) -> float:
        return self.high - self.low


@dataclass
class Signal:
    """一个技术事件。formed/confirmed/invalidated 三个时间戳是审计的命门。"""
    engine: str
    kind: str
    direction: str
    state: str = CANDIDATE
    formed_at: str = ""
    formed_idx: int = -1
    confirmed_at: str | None = None
    confirmed_idx: int | None = None
    invalidated_at: str | None = None
    invalidated_idx: int | None = None
    confirm_bars: int = 0
    price: float = 0.0
    strength: float = 0.0
    scope: str = SCOPE_EVENT
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EngineResult:
    engine: str
    ok: bool
    signals: list[Signal] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "ok": self.ok,
            "signals": [s.to_dict() for s in self.signals],
            "metrics": self.metrics,
            "notes": self.notes,
            "error": self.error,
        }


@dataclass
class GuardReport:
    """防未来函数体检结果（机制 M2）。"""
    engine: str
    passed: bool
    total_signals: int = 0
    mismatched: int = 0
    lookahead_violations: int = 0
    confirm_violations: int = 0
    samples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfluenceState:
    trend: str = NEUTRAL
    structure: str = "unknown"
    volume_price: str = "unknown"
    timeliness: str = "unknown"
    conclusion: str = CONF_NONE
    score: int = 0
    votes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreCard:
    dims: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    total: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"dims": self.dims, "weights": self.weights, "total": self.total}


@dataclass
class Profile:
    code: str
    name: str
    industry: str
    as_of: str
    bar_count: int
    data_start: str
    data_end: str
    close: float
    engines: dict[str, EngineResult]
    guard: dict[str, GuardReport]
    confluence: ConfluenceState
    scorecard: ScoreCard
    data_quality: dict[str, Any] = field(default_factory=dict)
    verdict: str = ""
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "industry": self.industry,
            "as_of": self.as_of,
            "bar_count": self.bar_count,
            "data_start": self.data_start,
            "data_end": self.data_end,
            "close": self.close,
            "engines": {k: v.to_dict() for k, v in self.engines.items()},
            "guard": {k: v.to_dict() for k, v in self.guard.items()},
            "confluence": self.confluence.to_dict(),
            "scorecard": self.scorecard.to_dict(),
            "data_quality": self.data_quality,
            "verdict": self.verdict,
            "risks": self.risks,
        }
