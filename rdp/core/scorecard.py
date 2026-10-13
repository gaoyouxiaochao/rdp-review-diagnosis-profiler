# -*- coding: utf-8 -*-
"""六维评分卡（机制 M3）。权重默认沿用比选阶段的 25/20/20/15/10/10，可配置。

评分对象是"本次诊断的可信度"，不是给股票打分、也不构成投资评级。
"""
from __future__ import annotations

from ..schema import EngineResult, GuardReport, ScoreCard, Profile, Signal, CONFIRMED

DEFAULT_WEIGHTS = {
    "算法完整性": 25,
    "信号可靠性": 20,
    "工程可集成性": 20,
    "测试与验证": 15,
    "A股适配性": 10,
    "许可证与维护": 10,
}

MAX_SCORE = 5.0


def evaluate(
    engines: dict[str, EngineResult],
    guards: dict[str, GuardReport],
    quality: dict,
    signals: list[Signal],
    weights: dict[str, float] | None = None,
) -> ScoreCard:
    w = dict(weights or DEFAULT_WEIGHTS)
    total_w = sum(w.values()) or 100.0

    # 1 算法完整性：引擎可用率
    ok_n = sum(1 for r in engines.values() if r.ok)
    all_n = max(len(engines), 1)
    s1 = MAX_SCORE * ok_n / all_n

    # 2 信号可靠性：防护检通过率 + 已确认占比
    if guards:
        passed = sum(1 for g in guards.values() if g.passed)
        s2a = MAX_SCORE * passed / len(guards)
    else:
        s2a = 0.0
    if signals:
        conf_ratio = sum(1 for s in signals if s.state == CONFIRMED) / len(signals)
        s2 = round(s2a * 0.7 + MAX_SCORE * conf_ratio * 0.3, 2)
    else:
        s2 = round(s2a * 0.7, 2)

    # 3 工程可集成性：输出契约完整性
    need = {"engine", "kind", "direction", "state", "formed_at", "price", "evidence"}
    if signals:
        full = sum(1 for s in signals
                   if not (need - set(s.to_dict().keys())) and s.evidence)
        s3 = round(MAX_SCORE * full / len(signals), 2)
    else:
        s3 = 0.0

    # 4 测试与验证：证据链完整率
    if signals:
        with_ev = sum(1 for s in signals if s.evidence and s.formed_at)
        s4 = round(MAX_SCORE * with_ev / len(signals), 2)
    else:
        s4 = 0.0

    # 5 A股适配性：数据质量
    if not quality or not quality.get("ok"):
        s5 = 0.0
    else:
        bars = max(quality.get("bars", 1), 1)
        bad = quality.get("bad_bars", 0) + quality.get("zero_volume_days", 0)
        s5 = round(max(0.0, MAX_SCORE * (1 - bad / bars)), 2)

    # 6 许可证与维护：全自研、无外部代码依赖 = 满分
    s6 = MAX_SCORE

    dims = {
        "算法完整性": round(s1, 2),
        "信号可靠性": round(s2, 2),
        "工程可集成性": round(s3, 2),
        "测试与验证": round(s4, 2),
        "A股适配性": round(s5, 2),
        "许可证与维护": round(s6, 2),
    }
    total = round(sum(dims[k] * w[k] for k in dims) / total_w * 20.0, 2)
    return ScoreCard(dims=dims, weights=w, total=total)


def verdict_of(p: Profile) -> tuple[str, list[str]]:
    """结论与风险提示。只描述技术状态，不构成任何投资建议。"""
    risks: list[str] = []
    for g in p.guard.values():
        if not g.passed:
            risks.append(f"{g.engine} 未通过防未来函数体检（不一致 {g.mismatched} 条 / 确认违规 {g.confirm_violations} 条）")
    if p.scorecard.total < 60:
        risks.append("诊断置信度偏低，结论仅供参考")
    if p.data_quality.get("zero_volume_days"):
        risks.append(f"存在 {p.data_quality['zero_volume_days']} 个零成交日（停牌或数据缺失）")
    if any((not r.ok) for r in p.engines.values()):
        risks.append("部分引擎数据不足，画像不完整")

    label = {
        "bull_confluence": "看涨共振",
        "bear_confluence": "看跌共振",
        "divergence": "多空分歧",
        "no_confluence": "无有效共振",
    }.get(p.confluence.conclusion, "无有效共振")

    verdict = f"{label}（共振分 {p.confluence.score:+d} / 置信度 {p.scorecard.total:.1f}）"
    return verdict, risks
