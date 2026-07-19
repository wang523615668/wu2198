#!/usr/bin/env python3
"""
Minimal post-TF-recovery sync for wu2198 v2.

The full historical pipeline (common.py / SECTOR_LEADERS / notify_updates)
was lost with the TF card. This stub keeps the intraday cron healthy by:
1. reading all events/*.jsonl
2. writing reports/point_levels.json
3. writing a lightweight watchlist.json skeleton from text heuristics

Primary live pool data still comes from weibo_live_stock_pool.py /
cron_weibo_fetch.sh under /root/.hermes/state/.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

V2_DIR = Path("/vol1/1000/openzl/wu2198/v2")
EVENTS_DIR = V2_DIR / "events"
REPORTS_DIR = V2_DIR / "reports"
WATCHLIST_JSON = V2_DIR / "watchlist.json"
WATCHLIST_MD = V2_DIR / "watchlist.md"
RUNTIME_STATE = V2_DIR / "runtime_state.json"

THEME_KEYWORDS = {
    "创新药": ["创新药", "医药", "生物", "医疗", "CXO", "恒瑞"],
    "半导体": ["半导体", "芯片", "中芯", "华创", "存储"],
    "CPO": ["CPO", "光模块", "中际旭创", "新易盛", "天孚"],
    "PCB": ["PCB", "覆铜板", "铜箔"],
    "白酒": ["白酒", "茅台", "五粮液", "汾酒"],
    "军工": ["军工", "航天", "航空"],
    "固态电池": ["固态电池", "锂矿", "电解液", "前驱体"],
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_all_events() -> list[dict]:
    events: list[dict] = []
    if not EVENTS_DIR.exists():
        return events
    for ef in sorted(EVENTS_DIR.glob("*.jsonl")):
        for line in ef.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    # dedup by post_id / id
    seen: set[str] = set()
    out: list[dict] = []
    for ev in sorted(events, key=lambda e: e.get("created_ts") or e.get("created_at") or ""):
        key = str(ev.get("post_id") or ev.get("id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(ev)
    return out


def extract_points_from_event(ev: dict) -> list[int]:
    pts = []
    ss = ev.get("structure_signals") or {}
    if isinstance(ss, dict):
        raw = ss.get("points") or []
        if isinstance(raw, list):
            for x in raw:
                try:
                    pts.append(int(x))
                except Exception:
                    pass
    if pts:
        return sorted(set(pts))
    text = ev.get("text") or ""
    found = set()
    for m in re.finditer(r"(\d{4})点", text):
        v = int(m.group(1))
        if 2500 <= v <= 6000:
            found.add(v)
    for m in re.finditer(r"(\d{5})点", text):
        v = int(m.group(1))
        if 30000 <= v <= 60000:
            found.add(v)
    return sorted(found)


def build_point_levels(events: list[dict]) -> dict:
    point_levels = []
    for ev in events:
        pts = extract_points_from_event(ev)
        if not pts:
            continue
        point_levels.append(
            {
                "created_ts": ev.get("created_ts") or "",
                "created_at": ev.get("created_at") or "",
                "post_id": ev.get("post_id") or ev.get("id") or "",
                "points": pts,
                "text": (ev.get("text") or "")[:200],
                "vip": bool(ev.get("vip")),
            }
        )
    point_levels.sort(key=lambda x: x.get("created_ts") or "", reverse=True)
    return {
        "summary": {
            "generated_at": now_str(),
            "event_count": len(events),
            "point_level_count": len(point_levels),
        },
        "point_levels": point_levels,
    }


def infer_themes(text: str) -> list[str]:
    themes = []
    for theme, kws in THEME_KEYWORDS.items():
        if any(k in text for k in kws):
            themes.append(theme)
    return themes


def build_watchlist(events: list[dict]) -> dict:
    theme_counter: Counter[str] = Counter()
    recent = events[-200:] if len(events) > 200 else events
    for ev in recent:
        text = ev.get("text") or ""
        for t in infer_themes(text):
            theme_counter[t] += 1
        rec = ev.get("recommendation") or {}
        for t in rec.get("themes") or []:
            if isinstance(t, str) and t:
                theme_counter[t] += 1
            elif isinstance(t, dict):
                name = t.get("name") or t.get("theme")
                if name:
                    theme_counter[str(name)] += 1

    themes = [
        {"name": name, "mentions": count, "priority": min(100, 40 + count * 5)}
        for name, count in theme_counter.most_common(30)
    ]

    # Keep schema keys expected by older consumers
    return {
        "generated_at": now_str(),
        "source": "v2/sync_watchlist minimal (post-TF recovery)",
        "leaders": [],
        "candidates": [],
        "etfs": [],
        "themes": themes,
        "all_stocks": [],
        "event_count": len(events),
        "notes": "Full SECTOR_LEADERS pipeline not restored; themes from keyword scan only.",
    }


def write_watchlist_md(wl: dict) -> None:
    lines = [
        f"# wu2198 watchlist (minimal)",
        f"",
        f"- generated_at: {wl.get('generated_at')}",
        f"- event_count: {wl.get('event_count')}",
        f"- themes: {len(wl.get('themes') or [])}",
        f"",
        f"## Themes",
    ]
    for t in wl.get("themes") or []:
        lines.append(f"- {t.get('name')}: mentions={t.get('mentions')}")
    WATCHLIST_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    events = load_all_events()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    point_report = build_point_levels(events)
    (REPORTS_DIR / "point_levels.json").write_text(
        json.dumps(point_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # lightweight companions so paths exist
    structure_events = {
        "generated_at": now_str(),
        "events": [
            {
                "created_ts": e.get("created_ts"),
                "post_id": e.get("post_id") or e.get("id"),
                "points": extract_points_from_event(e),
                "text": (e.get("text") or "")[:120],
            }
            for e in events
            if extract_points_from_event(e)
        ][-100:],
    }
    (REPORTS_DIR / "structure_events.json").write_text(
        json.dumps(structure_events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (REPORTS_DIR / "trend_states.json").write_text(
        json.dumps(
            {
                "generated_at": now_str(),
                "bias": "unknown",
                "note": "minimal stub after TF recovery",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    wl = build_watchlist(events)
    WATCHLIST_JSON.write_text(json.dumps(wl, ensure_ascii=False, indent=2), encoding="utf-8")
    write_watchlist_md(wl)

    runtime = {}
    if RUNTIME_STATE.exists():
        try:
            runtime = json.loads(RUNTIME_STATE.read_text(encoding="utf-8"))
        except Exception:
            runtime = {}
    runtime.update(
        {
            "last_run": now_str(),
            "last_watchlist_sync_ok": True,
            "last_pipeline_ok": True,
            "last_error": None,
            "last_event_count": len(events),
            "last_point_level_count": point_report["summary"]["point_level_count"],
            "watchlist_path": str(WATCHLIST_JSON),
            "point_levels_path": str(REPORTS_DIR / "point_levels.json"),
            "sync_mode": "minimal_post_tf_recovery",
        }
    )
    RUNTIME_STATE.write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding="utf-8")

    # Do NOT print absolute file paths — Hermes cron delivery auto-attaches
    # paths like /.../watchlist.json to WeChat. Summary text only.
    print(
        f"watchlist_sync ok "
        f"leaders={len(wl.get('leaders') or [])} "
        f"candidates={len(wl.get('candidates') or [])} "
        f"etfs={len(wl.get('etfs') or [])} "
        f"themes={len(wl.get('themes') or [])} "
        f"events={len(events)} "
        f"points={point_report['summary']['point_level_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
