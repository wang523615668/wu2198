#!/usr/bin/env python3
"""
Bridge: fetch wu2198 posts via guest session (fetch_weibo.py)
and ingest into v2 event pipeline for point extraction.
No WEIBO_COOKIE needed.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

V2_DIR = Path("/vol1/1000/openzl/wu2198/v2")
ANALYZER_DIR = Path("/vol1/1000/openzl/wu2198/analyzer")
EVENTS_DIR = V2_DIR / "events"

WU2198_UID = "1216826604"


def parse_weibo_time(time_str: str) -> datetime | None:
    """Parse weibo time format like 'Fri Jul 03 06:57:48 +0800 2026'."""
    if not time_str:
        return None
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(time_str, fmt)
        except Exception:
            continue
    # relative-ish fallbacks like '今天 09:12' are not trusted for event dating
    return None


def extract_points(text: str) -> list[int]:
    """Extract numeric index points from text (A股 4-digit + 道指 5-digit)."""
    points: set[int] = set()
    patterns_a = [
        r"大盘指数[收在突破跌破试了约到]*(\d{4})",
        r"指数.*?(\d{4})点",
        r"[收在突破跌破试了约到]*(\d{4})点",
    ]
    for pat in patterns_a:
        for m in re.finditer(pat, text or ""):
            pt = int(m.group(1))
            if 2500 <= pt <= 6000:
                # skip year-like numbers if followed by 年
                end = m.end(1)
                if end < len(text) and text[end] == "年":
                    continue
                points.add(pt)

    patterns_us = [
        r"试了(\d{5})点",
        r"(\d{5})点",
    ]
    for pat in patterns_us:
        for m in re.finditer(pat, text or ""):
            pt = int(m.group(1))
            if 30000 <= pt <= 60000:
                points.add(pt)
    return sorted(points)


def fetch_latest_posts(pages: int = 3) -> list[dict]:
    """Fetch using the existing fetch_weibo.py module (guest session)."""
    sys.path.insert(0, str(ANALYZER_DIR))
    from fetch_weibo import fetch_wu2198  # type: ignore

    raw_posts = fetch_wu2198(pages=pages, invest_only=True)
    posts: list[dict] = []
    for p in raw_posts:
        mid = str(p.get("mid", p.get("id", "")) or "")
        posts.append(
            {
                "post_id": mid,
                "text": p.get("text", "") or "",
                "created_at": p.get("created_at", "") or "",
                "url": p.get("url")
                or (f"https://m.weibo.cn/status/{mid}" if mid else ""),
            }
        )
    return posts


def ingest_to_events(posts: list[dict]) -> int:
    """Convert posts to v2 event format and write to daily event files."""
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    count = 0

    # preload existing ids per date file to avoid reopening for every post
    existing_by_file: dict[Path, set[str]] = {}

    for post in posts:
        dt = parse_weibo_time(post.get("created_at", ""))
        if not dt:
            continue

        date_str = dt.strftime("%Y-%m-%d")
        event_file = EVENTS_DIR / f"{date_str}.jsonl"

        if event_file not in existing_by_file:
            existing_ids: set[str] = set()
            if event_file.exists():
                with open(event_file, encoding="utf-8") as f:
                    for line in f:
                        try:
                            ev = json.loads(line)
                            existing_ids.add(str(ev.get("post_id", "") or ""))
                        except Exception:
                            pass
            existing_by_file[event_file] = existing_ids

        post_id = str(post.get("post_id", "") or "")
        if not post_id or post_id in existing_by_file[event_file]:
            continue

        points = extract_points(post.get("text", ""))
        event = {
            "id": f"guest_{post_id}",
            "post_id": post_id,
            "created_at": post.get("created_at", ""),
            "created_ts": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "text": post.get("text", ""),
            "url": post.get("url", ""),
            "source_user": "wu2198",
            "source_uid": WU2198_UID,
            "source_bid": "",
            "view_type": "游客态公开",
            "vip": False,
            "sectors": [],
            "levels": [],
            "level_type": None,
            "structure_signals": {
                "points": points,
            },
            "notes": "游客态自动抓取",
        }

        with open(event_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        existing_by_file[event_file].add(post_id)
        count += 1

    return count


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Fetching wu2198 posts (guest session, {args.pages} pages)...")
    posts = fetch_latest_posts(pages=args.pages)
    print(f"Fetched {len(posts)} investment-related posts")

    if args.dry_run:
        for p in posts[:10]:
            pts = extract_points(p.get("text", ""))
            created = (p.get("created_at") or "")[:25]
            text = (p.get("text") or "")[:80]
            print(f"  {created} | pts={pts} | {text}")
        return 0

    count = ingest_to_events(posts)
    print(f"Ingested {count} new events into v2 pipeline")

    # Dashboard cache (best-effort; live pool cron is the primary path)
    try:
        output_path = ANALYZER_DIR / "data" / "wu2198_latest.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"warn: failed to write wu2198_latest.json: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
