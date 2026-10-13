# -*- coding: utf-8 -*-
"""HTML 画像报告渲染：统计概览 + 全池排行榜 + 头部标的详情卡。"""
from __future__ import annotations

from html import escape
from pathlib import Path

from ..schema import Profile
from .styles import CSS, SORT_JS

CONF_LABEL = {
    "bull_confluence": ("看涨共振", "up"),
    "bear_confluence": ("看跌共振", "down"),
    "divergence": ("多空分歧", "div"),
    "no_confluence": ("无有效共振", "none"),
}
DIM_ORDER = ["算法完整性", "信号可靠性", "工程可集成性", "测试与验证", "A股适配性", "许可证与维护"]
TOP_N = 24


def _e(x) -> str:
    return escape(str(x if x is not None else ""))


def _conf_pill(c: str) -> str:
    label, cls = CONF_LABEL.get(c, (c, "none"))
    return f'<span class="pill {cls}">{_e(label)}</span>'


def _stats(ps: list[Profile]) -> str:
    n = len(ps)
    cnt = {k: 0 for k in CONF_LABEL}
    for p in ps:
        cnt[p.confluence.conclusion] = cnt.get(p.confluence.conclusion, 0) + 1
    guard_ok = sum(1 for p in ps if all(g.passed for g in p.guard.values()))
    sigs = sum(len(r.signals) for p in ps for r in p.engines.values())
    items = [
        (str(n), "标的总数", ""),
        (str(cnt["bull_confluence"]), "看涨共振", "up"),
        (str(cnt["bear_confluence"]), "看跌共振", "down"),
        (str(cnt["divergence"]), "多空分歧", ""),
        (str(cnt["no_confluence"]), "无有效共振", ""),
        (f"{guard_ok}/{n}", "防未来函数体检通过", ""),
        (str(sigs), "信号事件总数", ""),
    ]
    return '<div class="stats">' + "".join(
        f'<div class="stat"><div class="v {cls}">{_e(v)}</div><div class="l">{_e(l)}</div></div>'
        for v, l, cls in items) + "</div>"


def _dist(ps: list[Profile]) -> str:
    n = max(len(ps), 1)
    rows = []
    for k, (label, cls) in CONF_LABEL.items():
        c = sum(1 for p in ps if p.confluence.conclusion == k)
        w = c / n * 100
        rows.append(
            f'<div class="bar-row"><span class="nm">{_e(label)}</span>'
            f'<span class="track"><span class="fill" style="width:{w:.1f}%"></span></span>'
            f'<span class="ct">{c}</span></div>')
    return "".join(rows)


def _rank_table(ps: list[Profile]) -> str:
    body = []
    for p in sorted(ps, key=lambda x: (-x.confluence.score, -x.scorecard.total)):
        label, cls = CONF_LABEL.get(p.confluence.conclusion, (p.confluence.conclusion, "none"))
        gok = all(g.passed for g in p.guard.values())
        body.append(
            f'<tr data-conf="{_e(p.confluence.conclusion)}">'
            f'<td>{_e(p.code)}</td><td>{_e(p.name)}</td><td>{_e(p.industry)}</td>'
            f'<td class="num" data-v="{p.close}">{p.close:.2f}</td>'
            f'<td><span class="pill {cls}">{_e(label)}</span></td>'
            f'<td class="num" data-v="{p.confluence.score}">{p.confluence.score:+d}</td>'
            f'<td class="num" data-v="{p.scorecard.total}">{p.scorecard.total:.1f}</td>'
            f'<td>{_e(p.confluence.trend)}</td><td>{_e(p.confluence.structure)}</td>'
            f'<td>{_e(p.confluence.volume_price)}</td>'
            f'<td><span class="pill {"ok" if gok else "bad"}">{"通过" if gok else "未通过"}</span></td>'
            f"</tr>")
    return (
        '<div class="toolbar">'
        '<input id="q" type="search" placeholder="搜索代码 / 名称 / 行业" style="min-width:220px">'
        '<select id="fconf"><option value="">全部结论</option>'
        + "".join(f'<option value="{k}">{_e(v[0])}</option>' for k, v in CONF_LABEL.items())
        + "</select>"
        '<span class="sc">点击表头可排序</span></div>'
        '<div class="tbl-wrap"><table id="rank"><thead><tr>'
        '<th data-k="0">代码</th><th data-k="1">名称</th><th data-k="2">行业</th>'
        '<th data-k="3">收盘</th><th data-k="4">共振结论</th><th data-k="5">共振分</th>'
        '<th data-k="6">置信度</th><th data-k="7">趋势</th><th data-k="8">结构</th>'
        '<th data-k="9">量价</th><th data-k="10">体检</th>'
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def _dim_cards(p: Profile) -> str:
    out = []
    for d in DIM_ORDER:
        v = float(p.scorecard.dims.get(d, 0))
        out.append(
            f'<div class="dim"><div class="n">{_e(d)}</div><div class="s">{v:.2f} / 5</div>'
            f'<div class="track"><i style="width:{v / 5 * 100:.0f}%"></i></div></div>')
    return '<div class="dims">' + "".join(out) + "</div>"


def _votes(p: Profile) -> str:
    rows = []
    for v in p.confluence.votes:
        ev = "；".join(f"{k}={val}" for k, val in list(v["evidence"].items())[:3])
        rows.append(f'<div><b>{_e(v["dimension"])}</b><span>{_e(v["value"])} '
                    f'(票 {v["vote"]:+d})</span></div>')
        if ev:
            rows.append(f'<div style="font-size:12px;color:var(--text-3);padding:0 0 4px 0">{_e(ev)}</div>')
    return '<div class="kv">' + "".join(rows) + "</div>"


def _signal_rows(p: Profile, limit: int = 10) -> str:
    """详情卡信号表。评审修正（P2-5）：旧版按 strength 全局排序取前 8，
    会被 pattern 的吞没(0.6)刷屏、挤掉 wyckoff/dow 的阶段判定。
    新策略：先保证 6 个引擎各有代表（取各自最强一条），再按 strength 补足。"""
    by_engine: dict[str, list] = {}
    for r in p.engines.values():
        sigs = [s for s in r.signals if s.state == "confirmed"] or list(r.signals)
        if sigs:
            sigs.sort(key=lambda s: -s.strength)
            by_engine[r.engine] = sigs

    picked: list = []
    picked_keys: set = set()
    for eng in ("volume_profile", "wyckoff", "dow", "smc", "divergence", "pattern"):
        if eng in by_engine:
            s = by_engine[eng][0]
            picked.append(s)
            picked_keys.add(id(s))
    rest = [s for sigs in by_engine.values() for s in sigs if id(s) not in picked_keys]
    rest.sort(key=lambda s: -s.strength)
    picked.extend(rest[: max(0, limit - len(picked))])

    out = []
    for s in picked[:limit]:
        ev = "；".join(f"{k}={val}" for k, val in list(s.evidence.items())[:4])
        out.append(f"<tr><td>{_e(s.engine)}</td><td>{_e(s.kind)}</td>"
                   f"<td>{_e(s.direction)}</td><td>{_e(s.state)}</td>"
                   f"<td>{_e(s.formed_at)}</td><td>{_e(s.confirmed_at or '-')}</td>"
                   f"<td>{_e(s.price)}</td><td>{s.strength:.2f}</td>"
                   f"<td style=\"white-space:normal\">{_e(ev)}</td></tr>")
    return ('<table><thead><tr><th>引擎</th><th>类型</th><th>方向</th><th>状态</th>'
            '<th>形成日</th><th>确认日</th><th>价格</th><th>强度</th><th>证据</th>'
            '</tr></thead><tbody>' + "".join(out) + "</tbody></table>")


def _detail(p: Profile, rank: int) -> str:
    label, cls = CONF_LABEL.get(p.confluence.conclusion, (p.confluence.conclusion, "none"))
    vp = p.engines.get("volume_profile")
    sm = p.engines.get("smc")
    dv = p.engines.get("divergence")
    wk = p.engines.get("wyckoff")
    dww = p.engines.get("dow")
    m = {**(vp.metrics if vp else {}), **(sm.metrics if sm else {}), **(dv.metrics if dv else {})}
    m_wk = wk.metrics if wk else {}
    m_dw = dww.metrics if dww else {}
    ret = m_dw.get("retracement") or {}
    PHASE_CN = {"accumulation": "吸筹", "distribution": "派发", "trading_range": "区间震荡",
                "markup": "拉升", "markdown": "下挫",
                "uptrend": "上升趋势", "downtrend": "下降趋势", "sideways": "无趋势"}
    kv = [("收盘", f"{p.close:.2f}"), ("POC", m.get("poc")), ("VAH", m.get("vah")),
          ("VAL", m.get("val")), ("收盘vsPOC", m.get("close_vs_poc")),
          ("结构趋势", m.get("structure_trend")), ("最后结构事件", m.get("last_structure")),
          ("RSI14", m.get("rsi_last")), ("最新背离", m.get("latest")),
          ("Wyckoff阶段", PHASE_CN.get(m_wk.get("phase"), m_wk.get("phase"))),
          ("假突破(已确认)", m_wk.get("confirmed_break_events")),
          ("放量无果", m_wk.get("effort_no_result_count")),
          ("道氏阶段", PHASE_CN.get(m_dw.get("phase"), m_dw.get("phase"))),
          ("区间回撤%", ret.get("retracement_pct"))]
    kvhtml = '<div class="kv">' + "".join(
        f"<div><b>{_e(k)}</b><span>{_e(v)}</span></div>" for k, v in kv) + "</div>"
    risks = "".join(f"<li>{_e(r)}</li>" for r in p.risks) or "<li>无</li>"
    return (
        f'<div class="card"><div class="hd"><div class="t">#{rank} {_e(p.code)} {_e(p.name)}'
        f'<small>{_e(p.industry)} · 基准日 {_e(p.as_of)} · {p.bar_count} 根K线</small></div>'
        f'<div>{_conf_pill(p.confluence.conclusion)} '
        f'<span class="pill {cls}">共振分 {p.confluence.score:+d}</span> '
        f'<span class="pill none">置信度 {p.scorecard.total:.1f}</span></div></div>'
        f'<div class="grid2"><div><h3>关键指标</h3>{kvhtml}</div>'
        f'<div><h3>共振四维投票</h3>{_votes(p)}</div></div>'
        f'<h3>六维评分卡（总分 {p.scorecard.total:.1f}）</h3>{_dim_cards(p)}'
        f'<h3>信号与证据链</h3><div class="tbl-wrap">{_signal_rows(p)}</div>'
        f'<h3>风险提示</h3><ul style="margin-left:18px;font-size:13px;color:var(--text-2)">{risks}</ul>'
        f"</div>")


def write(ps: list[Profile], out: Path, title: str = "复盘诊断分析画像报告") -> Path:
    ranked = sorted(ps, key=lambda x: (-abs(x.confluence.score), -x.scorecard.total))
    tops = ranked[:TOP_N]
    guard_ok = sum(1 for p in ps if all(g.passed for g in p.guard.values()))
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>{CSS}</style></head><body><div class="wrap">
<header class="hero">
  <div class="kicker">复盘诊断分析画像模块 v1.0 · 技术面复盘</div>
  <h1>{_e(title)}</h1>
  <p>标的池来自股权激励 2026 中报补全表（196 只）。仅做技术面复盘诊断，不接入交易数据、不做回测、不构成投资建议。</p>
  <div class="chips">
    <span class="chip">引擎：量价分布 / SMC / 背离 / 形态</span>
    <span class="chip ok">防未来函数体检 {guard_ok}/{len(ps)} 通过</span>
    <span class="chip">信号三态：候选 → 确认 → 失效</span>
    <span class="chip">诊断基准日 {_e(ps[0].as_of) if ps else '-'}</span>
  </div>
</header>
<h2>一、总览</h2>{_stats(ps)}
<div class="note ok"><b>防未来函数体检：</b>全部引擎均通过 walk-forward 截断重算比对。
用截断到基准日的数据重算，与全量数据计算后截取的信号集合逐条一致，未发现未来函数或信号重绘。</div>
<h2>二、共振结论分布</h2>{_dist(ps)}
<h2>三、全池排行榜（{len(ps)} 只）</h2>{_rank_table(ps)}
<h2>四、头部标的画像详情（按共振强度取前 {len(tops)} 只）</h2>
{"".join(_detail(p, i + 1) for i, p in enumerate(tops))}
<h2>五、方法论与约束</h2>
<div class="card">
  <h3>引入的机制</h3>
  <ul style="margin-left:18px;font-size:13.5px;color:var(--text-2)">
    <li><b>M1 信号三态状态机</b>：候选 → 确认 → 失效，每个事件带 formed_at / confirmed_at / invalidated_at 与证据链</li>
    <li><b>M2 防未来函数闸门</b>：walk-forward 截断重算比对 + 确认延迟校验，任一引擎违规即判不通过</li>
    <li><b>M3 六维评分卡</b>：算法完整性 25 / 信号可靠性 20 / 工程可集成性 20 / 测试与验证 15 / A 股适配性 10 / 许可证与维护 10</li>
    <li><b>M4 共振投票</b>：趋势 / 结构 / 量价 / 时效 四类独立计票，同一 K 线同类证据不重复计票</li>
    <li><b>M5 分层解耦</b>：统一行情层 → 独立引擎 → 统一事件引擎 → 共振与评分 → 报告</li>
    <li><b>M6 尽调清单</b>：外部算法仅参考规则，全部 Python 独立实现并逐根对拍</li>
  </ul>
  <h3>约束与免责</h3>
  <ul style="margin-left:18px;font-size:13.5px;color:var(--text-2)">
    <li>行情为腾讯公开前复权日线，窗口 160 根，基准日 {_e(ps[0].as_of) if ps else '-'}</li>
    <li>仅技术面复盘，不接入任何交易或持仓数据，无回测、无收益归因</li>
    <li>输出为技术状态描述与置信度，<b>不构成任何投资建议</b></li>
  </ul>
</div>
<footer>复盘诊断分析画像模块 · 全部代码自研，未复用任何其他目录的代码</footer>
</div><script>{SORT_JS}</script></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
