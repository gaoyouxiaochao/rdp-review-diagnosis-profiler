# -*- coding: utf-8 -*-
"""行情抓取：腾讯公开前复权日线接口。全模块唯一取数入口，数据不进对话上下文。

评审修正（P1-3）：
- 改 https（旧 http 会被腾讯 302 到 https，白绕一跳）；
- 全局限流：每个请求间隔 MIN_INTERVAL 秒，避免 196 只连抓触发 WAF 501 限流；
- 指数退避重试 + 结束输出失败清单，便于二次补抓。

用法：
    python tools/fetch_klines.py --all
    python tools/fetch_klines.py --code 002245
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KLINE_DIR = ROOT / "data" / "klines"
TARGETS = ROOT / "data" / "targets.json"

API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sec},day,,,{n},qfq"
BARS = 160
WORKERS = 4            # 评审修正：8 -> 4，配合限流，降低 WAF 触发概率
RETRY = 3              # 评审修正：2 -> 3
MIN_INTERVAL = 0.25    # 全局最小请求间隔（秒）
BACKOFF = (1.0, 2.0, 4.0)

CST = timezone(timedelta(hours=8))

_rate_lock = threading.Lock()
_last_ts = 0.0


def _throttle() -> None:
    """全局限流：保证任意两个请求间隔 >= MIN_INTERVAL。"""
    global _last_ts
    with _rate_lock:
        now = time.monotonic()
        wait = MIN_INTERVAL - (now - _last_ts)
        if wait > 0:
            time.sleep(wait)
        _last_ts = time.monotonic()


def _get(url: str) -> dict:
    _throttle()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def fetch_one(item: dict, force: bool = False) -> tuple[str, str]:
    code, sec, name = item["code"], item["sec"], item.get("name", "")
    out = KLINE_DIR / f"{code}.json"
    if out.exists() and not force:
        return code, "skip"

    last_err = ""
    for attempt in range(RETRY):
        try:
            raw = _get(API.format(sec=sec, n=BARS))
            node = raw.get("data", {}).get(sec, {})
            rows = node.get("qfqday") or node.get("day") or []
            if not rows:
                last_err = "empty rows"
                time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                continue
            bars = []
            for r in rows:
                bars.append({
                    "date": r[0],
                    "open": float(r[1]),
                    "close": float(r[2]),
                    "high": float(r[3]),
                    "low": float(r[4]),
                    "volume": float(r[5]),
                    # amount：该接口不返回成交额，置 None 而非伪造 0.0（评审 P2-4）
                    "amount": None,
                })
            bars.sort(key=lambda b: b["date"])
            payload = {
                "code": code,
                "name": name,
                "industry": item.get("industry", ""),
                "sec": sec,
                "source": "tencent ifzq qfq day",
                "fetched_at": datetime.now(CST).isoformat(timespec="seconds"),
                "bar_count": len(bars),
                "start": bars[0]["date"],
                "end": bars[-1]["date"],
                "bars": bars,
            }
            out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return code, "ok"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
    return code, f"fail:{last_err}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--code", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    KLINE_DIR.mkdir(parents=True, exist_ok=True)
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))
    if args.code:
        targets = [t for t in targets if t["code"] == args.code]
    if not targets:
        print("no targets")
        return 1

    ok = skip = fail = 0
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, t, args.force): t for t in targets}
        for f in as_completed(futs):
            code, st = f.result()
            if st == "ok":
                ok += 1
            elif st == "skip":
                skip += 1
            else:
                fail += 1
                failed.append(f"{code}({st})")
    print(f"ok={ok} skip={skip} fail={fail}")
    if failed:
        print("failed:", ", ".join(failed[:20]))
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
