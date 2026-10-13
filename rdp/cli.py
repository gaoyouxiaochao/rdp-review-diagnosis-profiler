# -*- coding: utf-8 -*-
"""命令行入口。

    python -m rdp.cli --all
    python -m rdp.cli --code 002245
    python -m rdp.cli --all --as-of 2026-09-30
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rdp.core.pipeline import build, build_all, AS_OF, ENGINE_FNS   # noqa: E402
from rdp.report.render_excel import write as write_excel       # noqa: E402
from rdp.report.render_html import write as write_html         # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="复盘诊断分析画像模块")
    ap.add_argument("--all", action="store_true", help="全池")
    ap.add_argument("--code", default="", help="单只代码")
    ap.add_argument("--as-of", default=AS_OF, help="诊断基准日 YYYY-MM-DD")
    ap.add_argument("--outdir", default="output", help="输出目录")
    args = ap.parse_args()

    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    if args.code:
        p = build(args.code, as_of=args.as_of)
        profiles = [p]
    elif args.all:
        targets = json.loads((ROOT / "data" / "targets.json").read_text(encoding="utf-8"))
        profiles, failed = build_all(targets, args.as_of)
        if failed:
            print(f"[warn] {len(failed)} 只失败：{failed[:3]}")
    else:
        ap.error("需要 --all 或 --code")
        return 2

    payload = {
        "generated_at": args.as_of,
        "count": len(profiles),
        "engines": list(ENGINE_FNS.keys()),
        "profiles": [p.to_dict() for p in profiles],
    }
    jf = outdir / "profiles.json"
    jf.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    xf = write_excel(profiles, outdir / "复盘诊断画像_汇总.xlsx")
    hf = write_html(profiles, outdir / "复盘诊断画像报告.html")

    guard_bad = [p.code for p in profiles if any(not g.passed for g in p.guard.values())]
    print(f"profiles={len(profiles)}")
    print(f"json  -> {jf}")
    print(f"excel -> {xf}")
    print(f"html  -> {hf}")
    print(f"guard: pass={len(profiles) - len(guard_bad)} fail={len(guard_bad)} {guard_bad[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
