#!/usr/bin/env python3
"""
wu2198 微博股票分析看板 - FastAPI 后端
数据源：已有 weibo_live_stock_pool.json + master_stock_pool + 归档数据
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pandas as pd

# ── Wave Analysis ──
from wave_analysis import get_analysis
from chanlun import full_analysis
from indicators import full_technical_analysis
from wu_advisor import reconcile_with_wu, evaluate_stock_with_wu, daily_strategy, WU_VIEWPOINTS

# ── Paths ──
BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = Path("/root/.hermes/state")
STOCK_RESEARCH_DIR = Path("/vol1/1000/openzl/wu2198")
POOL_DIR = STOCK_RESEARCH_DIR / "stock_pool"
WEIBO_EXPORT_DIR = STOCK_RESEARCH_DIR / "weibo_export"

LIVE_POOL = STATE_DIR / "weibo_live_stock_pool.json"
MESSAGE_POOLS = STATE_DIR / "weibo_message_stock_pools.json"
POINT_TREND = STATE_DIR / "wu2198_point_trend_analysis.json"
VIP_MESSAGES = STATE_DIR / "wu2198_vip_messages.json"
MASTER_POOL = POOL_DIR / "wu2198_master_stock_pool.json"
MASTER_RANKED = POOL_DIR / "wu2198_master_stock_pool_ranked.json"

CST = timezone(timedelta(hours=8))

app = FastAPI(title="wu2198 微博股票分析")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))



def _stock_name(s: dict) -> str:
    return str(s.get("name") or s.get("stock_name") or "")


def _stock_code(s: dict) -> str:
    return str(s.get("code") or s.get("stock_code") or "")


def _stock_bucket(s: dict) -> str:
    return str(s.get("live_bucket") or s.get("bucket") or s.get("category") or "")


def _stock_sector(s: dict) -> str:
    themes = s.get("themes") or []
    return str(s.get("sector") or s.get("industry") or (themes[0] if themes else "") or "其他")


def _load_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _fmt_time(iso_str: str) -> str:
    """Format ISO time string to readable format"""
    try:
        if "+" in iso_str or "Z" in iso_str:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo:
            dt = dt.astimezone(CST)
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return iso_str[:16]


# ── API Routes ──

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/overview")
async def api_overview():
    """Dashboard overview: key metrics + sector distribution + recent signals"""
    live = _load_json(LIVE_POOL, {})
    master = _load_json(MASTER_POOL, {})
    trend = _load_json(POINT_TREND, {})
    vip = _load_json(VIP_MESSAGES, [])

    # Normalize trend - can be dict or list
    trend_items = []
    if isinstance(trend, dict):
        trend_items = trend.get("trend_analysis", trend.get("points", []))
        if not isinstance(trend_items, list):
            trend_items = [trend_items]
    elif isinstance(trend, list):
        trend_items = trend

    stocks = live.get("stocks", [])
    master_stocks = master.get("stocks", master.get("rows", []))

    # Sector distribution from live pool
    sector_map: dict[str, int] = {}
    for s in stocks:
        for theme in s.get("themes", []):
            sector_map[theme] = sector_map.get(theme, 0) + 1

    # Master pool sector distribution
    master_sectors: dict[str, int] = {}
    for s in master_stocks:
        sector = s.get("sector") or s.get("industry") or ""
        if not sector:
            themes = s.get("themes") or []
            sector = themes[0] if themes else "其他"
        if not sector:
            sector = "其他"
        master_sectors[sector] = master_sectors.get(sector, 0) + 1

    # Top stocks by score
    top_stocks = sorted(stocks, key=lambda x: x.get("score", 0), reverse=True)[:10]

    # Master pool top by weibo_mentions or total_mentions
    top_master = sorted(master_stocks, key=lambda x: x.get("weibo_mentions", x.get("total_mentions", 0)), reverse=True)[:15]

    # Recent VIP signals
    recent_vip = vip[:5] if isinstance(vip, list) else []

    # Point trend summary
    point_summary = []
    for pt in trend_items[:10]:
        point_summary.append({
            "time": _fmt_time(pt.get("time", pt.get("created_at", ""))),
            "direction": pt.get("direction", pt.get("trend", "中性")),
            "level": pt.get("level", pt.get("confidence", "")),
            "reason": pt.get("reason", pt.get("summary", ""))[:100],
        })

    return {
        "updated_at": _fmt_time(live.get("generated_at", "")),
        "live_stock_count": len(stocks),
        "master_stock_count": len(master_stocks),
        "sector_distribution": sector_map,
        "master_sector_distribution": master_sectors,
        "top_stocks": [{
            "name": s.get("name", ""),
            "code": s.get("code", ""),
            "score": s.get("score", 0),
            "bucket": s.get("bucket", ""),
            "themes": s.get("themes", []),
            "latest": _fmt_time(s.get("latest_created_at", "")),
            "latest_age_hours": s.get("latest_age_hours", 0),
        } for s in top_stocks],
        "top_master": [{
            "name": s.get("name", s.get("stock_name", "")),
            "code": s.get("code", s.get("stock_code", "")),
            "total_mentions": s.get("total_mentions", s.get("weibo_mentions", 0)),
            "sector": s.get("sector", s.get("industry", "")),
            "sub_sector": s.get("sub_sector", ""),
            "latest_mention": s.get("latest_mention_date", s.get("latest_created_at", "")),
        } for s in top_master],
        "point_trend": point_summary,
        "recent_vip": recent_vip,
    }


@app.get("/api/live-pool")
async def api_live_pool():
    """Full live stock pool data"""
    live = _load_json(LIVE_POOL, {})
    stocks = live.get("stocks", [])

    return {
        "generated_at": _fmt_time(live.get("generated_at", "")),
        "targets": live.get("targets", []),
        "theme_ranking": live.get("theme_ranking", []),
        "stocks": sorted(stocks, key=lambda x: x.get("score", 0), reverse=True),
    }


@app.get("/api/master-pool")
async def api_master_pool():
    """Full master stock pool with ranking"""
    master = _load_json(MASTER_POOL, {})
    ranked = _load_json(MASTER_RANKED, {})

    return {
        "master_stocks": master.get("stocks", []),
        "ranked_stocks": ranked.get("stocks") or ranked.get("ranked_stocks") or ranked.get("rows") or [],
        "ranked_at": ranked.get("ranked_at", ranked.get("generated_at", "")),
    }


@app.get("/api/sectors")
async def api_sectors():
    """Sector/板块 analysis - group stocks by theme"""
    live = _load_json(LIVE_POOL, {})
    master = _load_json(MASTER_POOL, {})
    ranked = _load_json(MASTER_RANKED, {})

    # Group by theme from live pool
    theme_groups: dict[str, list] = {}
    for s in live.get("stocks", []):
        for theme in s.get("themes", []):
            if theme not in theme_groups:
                theme_groups[theme] = []
            theme_groups[theme].append({
                "name": _stock_name(s),
                "code": _stock_code(s),
                "score": s.get("score", 0),
                "bucket": _stock_bucket(s),
            })

    # Group by sector from master pool
    sector_groups: dict[str, list] = {}
    for s in master.get("stocks", []):
        sector = s.get("sector", s.get("industry", "其他"))
        if sector not in sector_groups:
            sector_groups[sector] = []
        sector_groups[sector].append({
            "name": _stock_name(s),
            "code": _stock_code(s),
            "total_mentions": s.get("total_mentions", 0),
            "sub_sector": s.get("sub_sector", ""),
            "latest": s.get("latest_mention_date", ""),
        })

    # Sort groups by count
    theme_groups = dict(sorted(theme_groups.items(), key=lambda x: -len(x[1])))
    sector_groups = dict(sorted(sector_groups.items(), key=lambda x: -len(x[1])))

    return {
        "live_themes": theme_groups,
        "master_sectors": sector_groups,
    }


@app.get("/api/trend")
async def api_trend():
    """Point/点位 trend analysis"""
    trend = _load_json(POINT_TREND, {})
    if isinstance(trend, list):
        return {"points": trend, "raw": trend}
    points = trend.get("market_levels") or trend.get("points") or trend.get("trend_analysis") or []
    if isinstance(points, dict):
        points = [points]
    return {
        "points": points,
        "trend_analysis": trend.get("trend_analysis"),
        "generated_at": trend.get("generated_at"),
        "stock_pool_summary": trend.get("stock_pool_summary"),
        "vip_messages": trend.get("vip_messages") or [],
    }


@app.get("/api/messages")
async def api_messages():
    """Recent weibo messages with stock mentions"""
    msg_pools = _load_json(MESSAGE_POOLS, {})
    vip = _load_json(VIP_MESSAGES, [])
    return {
        "message_pools": msg_pools,
        "vip_messages": vip[:20],
    }


@app.get("/api/index-prediction")
async def api_index_prediction():
    """
    AI-powered index prediction based on wu2198 signals.
    Synthesizes point trends, sector momentum, and VIP messages.
    """
    live = _load_json(LIVE_POOL, {}) or {}
    trend = _load_json(POINT_TREND, {}) or {}
    master = _load_json(MASTER_POOL, {}) or {}
    ranked = _load_json(MASTER_RANKED, {}) or {}

    live_stocks = live.get("stocks") or []
    if not live_stocks:
        for mp in (live.get("message_pools") or []):
            live_stocks.extend(mp.get("stocks") or [])

    sector_momentum: dict[str, dict] = {}
    for s in live_stocks:
        themes = s.get("themes") or []
        if not themes:
            sec = _stock_sector(s)
            themes = [sec] if sec else ["其他"]
        for theme in themes:
            if theme not in sector_momentum:
                sector_momentum[theme] = {"score_sum": 0, "count": 0, "stocks": []}
            sector_momentum[theme]["score_sum"] += float(s.get("score") or s.get("live_score") or 0)
            sector_momentum[theme]["count"] += 1
            nm = _stock_name(s)
            if nm and nm not in sector_momentum[theme]["stocks"]:
                sector_momentum[theme]["stocks"].append(nm)

    top_sectors = sorted(
        sector_momentum.items(),
        key=lambda x: x[1]["score_sum"],
        reverse=True,
    )

    master_stocks = master.get("stocks") or master.get("rows") or []
    master_sector_strength: dict[str, dict] = {}
    for s in master_stocks:
        sector = _stock_sector(s)
        if sector not in master_sector_strength:
            master_sector_strength[sector] = {"count": 0, "mentions": 0, "stocks": []}
        master_sector_strength[sector]["count"] += 1
        master_sector_strength[sector]["mentions"] += int(
            s.get("total_mentions") or s.get("weibo_mentions") or s.get("mentions") or 0
        )
        nm = _stock_name(s)
        if nm and nm not in master_sector_strength[sector]["stocks"]:
            master_sector_strength[sector]["stocks"].append(nm)

    master_top = sorted(
        master_sector_strength.items(),
        key=lambda x: x[1]["mentions"],
        reverse=True,
    )[:10]

    trend_direction = "中性"
    trend_strength = "观望"
    if isinstance(trend, list) and trend:
        latest = trend[0] if isinstance(trend[0], dict) else {}
        trend_direction = latest.get("direction") or latest.get("trend") or "中性"
        trend_strength = latest.get("level") or latest.get("confidence") or "观望"
    elif isinstance(trend, dict):
        ta = trend.get("trend_analysis") or {}
        if isinstance(ta, dict):
            trend_direction = ta.get("bias") or ta.get("direction") or "中性"
            b = int(ta.get("bullish_signal_count") or 0)
            e = int(ta.get("bearish_signal_count") or 0)
            if b > e:
                trend_strength = "偏多信号偏多"
            elif e > b:
                trend_strength = "偏空信号偏多"
            else:
                trend_strength = "观望"
        levels = trend.get("market_levels") or []
        if levels and isinstance(levels[0], dict) and levels[0].get("point") is not None:
            trend_strength = f"{trend_strength} · 关键{levels[0].get('point')}"

    ranked_stocks = ranked.get("stocks") or ranked.get("ranked_stocks") or ranked.get("rows") or []

    def _norm_stock(s):
        return {
            "name": _stock_name(s),
            "code": _stock_code(s),
            "sector": _stock_sector(s),
            "bucket": _stock_bucket(s),
            "total_mentions": s.get("total_mentions") or s.get("weibo_mentions") or s.get("mentions") or 0,
        }

    recommendations = {
        "core": [_norm_stock(s) for s in ranked_stocks if "核心" in _stock_bucket(s)][:5],
        "elastic": [_norm_stock(s) for s in ranked_stocks if "弹性" in _stock_bucket(s)][:5],
        "watch": [_norm_stock(s) for s in ranked_stocks if "观察" in _stock_bucket(s)][:5],
    }
    if not any(recommendations.values()) and ranked_stocks:
        sorted_rs = sorted(
            ranked_stocks,
            key=lambda x: float(x.get("live_score") or x.get("total_mentions") or x.get("mentions") or 0),
            reverse=True,
        )
        recommendations["core"] = [_norm_stock(s) for s in sorted_rs[:5]]
        recommendations["elastic"] = [_norm_stock(s) for s in sorted_rs[5:10]]
        recommendations["watch"] = [_norm_stock(s) for s in sorted_rs[10:15]]

    top_picks = []
    for s in sorted(
        ranked_stocks,
        key=lambda x: float(
            x.get("total_mentions") or x.get("weibo_mentions") or x.get("live_score") or x.get("mentions") or 0
        ),
        reverse=True,
    )[:10]:
        top_picks.append(
            {
                "name": _stock_name(s),
                "code": _stock_code(s),
                "sector": _stock_sector(s),
                "total_mentions": s.get("total_mentions")
                or s.get("weibo_mentions")
                or s.get("mentions")
                or 0,
            }
        )

    return {
        "market_signal": {
            "direction": str(trend_direction),
            "strength": str(trend_strength),
            "live_stock_count": len(live_stocks),
            "master_stock_count": len(master_stocks),
        },
        "hot_sectors": [
            {
                "name": k,
                "momentum_score": round(float(v["score_sum"]), 1),
                "stock_count": v["count"],
                "stocks": v["stocks"][:5],
            }
            for k, v in top_sectors[:8]
        ],
        "sector_strength": [
            {
                "name": k,
                "total_mentions": v["mentions"],
                "stock_count": v["count"],
                "stocks": v["stocks"][:5],
            }
            for k, v in master_top
        ],
        "recommendations": recommendations,
        "top_picks": top_picks,
    }


@app.get("/api/sector-heatmap")
async def api_sector_heatmap():
    """板块轮动热力图 - 按sector聚合，返回每板块的stock_count, avg_score, total_mentions等"""
    live = _load_json(LIVE_POOL, {})
    master = _load_json(MASTER_POOL, {})

    stocks = live.get("stocks", [])
    master_stocks = master.get("stocks", master.get("rows", []))

    # ── 从 master pool 按 sector 聚合 ──
    sector_map: dict[str, dict] = {}
    for s in master_stocks:
        sector = s.get("sector") or s.get("industry") or ""
        if not sector:
            themes = s.get("themes") or []
            sector = themes[0] if themes else "其他"
        if not sector:
            sector = "其他"
        if sector not in sector_map:
            sector_map[sector] = {
                "stock_count": 0,
                "score_sum": 0.0,
                "total_mentions": 0,
                "stocks": [],
                "score_count": 0,
            }
        sector_map[sector]["stock_count"] += 1
        # live_score from master pool
        sc = s.get("live_score")
        if sc is not None:
            try:
                sector_map[sector]["score_sum"] += float(sc)
                sector_map[sector]["score_count"] += 1
            except (ValueError, TypeError):
                pass
        # total_mentions / weibo_mentions
        mentions = int(s.get("total_mentions", s.get("weibo_mentions", 0)))
        sector_map[sector]["total_mentions"] += mentions
        sector_map[sector]["stocks"].append({
            "name": s.get("name", s.get("stock_name", "")),
            "code": s.get("code", s.get("stock_code", "")),
            "score": sc,
            "mentions": mentions,
        })

    # ── 从 live pool 补充主题热度（用于 momentum_trend） ──
    theme_momentum: dict[str, float] = {}
    for s in stocks:
        score = s.get("score", 0)
        for theme in s.get("themes", []):
            try:
                theme_momentum[theme] = theme_momentum.get(theme, 0) + float(score)
            except (ValueError, TypeError):
                theme_momentum[theme] = theme_momentum.get(theme, 0)

    # Match theme_momentum to sector (fuzzy: look for sector name in themes or vice versa)
    # Simple approach: if sector name appears as a theme, use that score
    def _get_momentum(sector_name: str) -> str:
        # Check exact match in theme_momentum
        if sector_name in theme_momentum:
            m = theme_momentum[sector_name]
        else:
            # Check partial match
            matched = 0.0
            for t, v in theme_momentum.items():
                if sector_name in t or t in sector_name:
                    matched = max(matched, v)
            m = matched
        if m >= 200:
            return "strong_up"
        elif m >= 100:
            return "moderate_up"
        elif m >= 50:
            return "mild_up"
        else:
            return "neutral"

    sectors_out = []
    for name, data in sorted(sector_map.items(), key=lambda x: -x[1]["stock_count"]):
        avg_score = round(data["score_sum"] / data["score_count"], 1) if data["score_count"] > 0 else None
        top_stocks = sorted(
            data["stocks"],
            key=lambda x: float(x["score"] or 0) + x["mentions"],
            reverse=True
        )[:3]
        sectors_out.append({
            "name": name,
            "stock_count": data["stock_count"],
            "avg_score": avg_score,
            "total_mentions": data["total_mentions"],
            "top_stocks": [{"name": _stock_name(s), "code": _stock_code(s)} for s in top_stocks],
            "momentum_trend": _get_momentum(name),
        })

    return {"sectors": sectors_out}


@app.get("/api/stock-scan")
async def api_stock_scan():
    """个股技术面扫描 - master/live 池前15，东财K线 + 本地指标"""
    import urllib.request

    master = _load_json(MASTER_POOL, {})
    live = _load_json(LIVE_POOL, {})
    rows = master.get("stocks", master.get("rows", []))
    if not rows:
        rows = live.get("stocks", [])
    # normalize
    norm = []
    for r in rows:
        code = str(r.get("stock_code") or r.get("code") or "")
        name = r.get("stock_name") or r.get("name") or ""
        score = r.get("live_score", r.get("score", 0))
        try:
            score = float(score or 0)
        except Exception:
            score = 0
        if not code and not name:
            continue
        norm.append({"stock_code": code, "stock_name": name, "live_score": score, "sector": r.get("sector") or ""})
    top15 = sorted(norm, key=lambda x: x["live_score"], reverse=True)[:15]

    def em_klines(code: str, limit: int = 120):
        code = str(code).zfill(6) if str(code).isdigit() else str(code)
        if not code.isdigit():
            return []
        market = "1" if code.startswith(("5", "6", "9")) else "0"
        url = (
            "http://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={market}.{code}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
            "&klt=101&fqt=1&beg=20240101&end=20500101"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        raw = ((data.get("data") or {}).get("klines") or [])[-limit:]
        out = []
        for line in raw:
            p = line.split(",")
            out.append({
                "date": p[0],
                "open": float(p[1]),
                "close": float(p[2]),
                "high": float(p[3]),
                "low": float(p[4]),
                "volume": float(p[5]) if len(p) > 5 else 0,
            })
        return out

    results = []
    for r in top15:
        code = r["stock_code"]
        name = r["stock_name"]
        try:
            klines = em_klines(code)
            tech = full_technical_analysis(klines) if klines else {"error": "no_kline"}
            last = klines[-1] if klines else {}
            results.append({
                "code": code,
                "name": name,
                "sector": r.get("sector"),
                "live_score": r.get("live_score"),
                "close": last.get("close"),
                "date": last.get("date"),
                "tech": tech,
            })
        except Exception as e:
            results.append({"code": code, "name": name, "error": str(e)})
    return {"count": len(results), "stocks": results}



@app.get("/api/backtest")
async def api_backtest():
    """历史回测 - 从weibo_export归档中找到提及某股票的最早日期，计算5/10/20日后涨跌幅"""
    import akshare as ak
    import glob
    from collections import defaultdict

    export_dir = str(WEIBO_EXPORT_DIR)
    if not os.path.isdir(export_dir):
        return {"summary": {"note": f"归档目录不存在: {export_dir}", "count": 0}, "results": [], "rows": []}

    # ── 1. 读取所有 _summary.json 和 _stocks_verified.json 文件 ──
    all_mentions = defaultdict(lambda: {"earliest_date": None, "earliest_detail": None})

    # 优先读取 _clean_stock_mentions_*_summary.json 中的 details（它们有完整的数据）
    summary_files = sorted(glob.glob(os.path.join(export_dir, "*_clean_stock_mentions_*_summary.json")))
    for sf in summary_files:
        try:
            data = _load_json(Path(sf), {})
            if not data:
                continue
            details = data.get("details", [])
            for d in details:
                code = d.get("stock_code", "").strip()
                if not code or not code.isdigit():
                    continue
                name = d.get("stock_name", "").strip()
                created_at = d.get("created_at", "")
                if not created_at:
                    continue
                # Parse date - handle various formats like "Tue Apr 28 17:35:15 +0800 2026"
                mention_date = created_at
                key = code
                old = all_mentions[key].get("earliest_date")
                if old is None or created_at < old:
                    all_mentions[key] = {
                        "earliest_date": created_at,
                        "earliest_detail": created_at,
                        "name": name,
                        "code": code,
                    }
        except Exception:
            continue

    # 也读 _stocks_verified.json
    verified_files = sorted(glob.glob(os.path.join(export_dir, "*_stocks_verified.json")))
    for vf in verified_files:
        try:
            stocks = _load_json(Path(vf), [])
            if not isinstance(stocks, list):
                continue
            for s in stocks:
                code = s.get("stock_code", "").strip()
                if not code or not code.isdigit():
                    continue
                name = s.get("stock_name", "").strip()
                created_at = s.get("latest_created_at", "")
                if not created_at:
                    continue
                key = code
                old = all_mentions[key].get("earliest_date")
                if old is None or created_at < old:
                    all_mentions[key] = {
                        "earliest_date": created_at,
                        "earliest_detail": created_at,
                        "name": name,
                        "code": code,
                    }
        except Exception:
            continue

    if not all_mentions:
        return {"summary": {"note": "未从归档中找到含股票代码的提及数据", "count": 0}, "results": [], "rows": []}

    # ── 2. 取前20只股票做回测 ──
    mention_list = sorted(all_mentions.values(), key=lambda x: x["earliest_date"])[:20]

    results = []
    for item in mention_list:
        code = item["code"]
        name = item["name"]
        mention_raw = item["earliest_date"]

        # Parse the mention date into datetime
        mention_dt = None
        try:
            # Try "Tue Apr 28 17:35:15 +0800 2026" format
            mention_dt = datetime.strptime(mention_raw, "%a %b %d %H:%M:%S %z %Y")
        except (ValueError, TypeError):
            try:
                mention_dt = datetime.fromisoformat(mention_raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                try:
                    mention_dt = datetime.strptime(mention_raw, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    pass

        if mention_dt is None:
            continue

        # Get date string for akshare (YYYYMMDD)
        mention_date_str = mention_dt.strftime("%Y%m%d")
        # Also calculate end date (mention + 30 trading days buffer)
        end_dt = mention_dt + timedelta(days=60)
        end_date_str = end_dt.strftime("%Y%m%d")

        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=mention_date_str, end_date=end_date_str)
            if df is None or df.empty:
                continue

            # Parse the dataframe to find mention date and subsequent days
            # The dataframe uses columns like 日期, 开盘, 收盘, etc (Chinese)
            close_col = "收盘" if "收盘" in df.columns else "close"
            date_col = "日期" if "日期" in df.columns else "date"

            # Parse dates for comparison
            kline_dates = []
            kline_closes = []
            for _, row in df.iterrows():
                kline_dates.append(str(row[date_col]))
                kline_closes.append(float(row[close_col]))

            if len(kline_closes) < 2:
                continue

            # Find index of the first trading day on or after mention_date
            mention_idx = None
            for i, d_str in enumerate(kline_dates):
                # Both in YYYY-MM-DD or YYYYMMDD format
                d_clean = d_str.replace("-", "")[:8]
                if d_clean >= mention_date_str:
                    mention_idx = i
                    break

            if mention_idx is None or mention_idx >= len(kline_closes) - 1:
                continue

            price_then = kline_closes[mention_idx]

            # Calculate pct_5d, pct_10d, pct_20d
            def _pct_at(offset: int):
                idx = mention_idx + offset
                if idx < len(kline_closes):
                    return round((kline_closes[idx] - price_then) / price_then * 100, 2)
                return None

            pct_5d = _pct_at(5)
            pct_10d = _pct_at(10)
            pct_20d = _pct_at(20)

            results.append({
                "stock": name,
                "code": code,
                "mention_date": mention_raw[:16],
                "price_then": price_then,
                "pct_5d": pct_5d,
                "pct_10d": pct_10d,
                "pct_20d": pct_20d,
            })

        except Exception:
            continue

    # ── 3. 汇总统计 ──
    valid_results = [r for r in results if r["pct_5d"] is not None]
    n = len(valid_results)
    if n == 0:
        return {"results": results, "summary": {}}

    summary = {}
    for period in ["pct_5d", "pct_10d", "pct_20d"]:
        vals = [r[period] for r in valid_results if r[period] is not None]
        if vals:
            win_rate = round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1)
            avg_pct = round(sum(vals) / len(vals), 2)
            max_pct = round(max(vals), 2)
            min_pct = round(min(vals), 2)
            summary[f"win_rate_{period}"] = win_rate
            summary[f"avg_pct_{period}"] = avg_pct
            summary[f"max_pct_{period}"] = max_pct
            summary[f"min_pct_{period}"] = min_pct

    return {"results": results, "summary": summary}


@app.get("/api/stock-analysis")
async def api_stock_analysis(name: str = "", code: str = ""):
    """任意股票技术分析 - 输入名称或代码，返回完整技术指标+缠论+评分"""
    import akshare as ak
    import asyncio
    import urllib.parse
    
    if not code and not name:
        return {"error": "请提供股票名称或代码"}
    
    # 名称→代码：用东方财富搜索API（毫秒级）
    if not code and name:
        try:
            import requests as _req
            encoded = urllib.parse.quote(name)
            search_url = f"https://searchapi.eastmoney.com/api/suggest/get?input={encoded}&type=14&token=D43BF722C8E33BDC906FB84D85E326E8"
            resp = _req.get(search_url, timeout=5)
            data = resp.json()
            items = data.get("QuotationCodeTable", {}).get("Data", [])
            a_stocks = [i for i in items if i.get("Classify") == "AStock"]
            if not a_stocks:
                return {"error": f"未找到A股 '{name}'，请直接输入6位代码"}
            code = a_stocks[0]["Code"]
            name = a_stocks[0]["Name"]
        except Exception as e:
            return {"error": f"搜索失败: {e}，请直接输入6位股票代码"}
    elif code and not name:
        try:
            import requests as _req
            encoded = urllib.parse.quote(code)
            search_url = f"https://searchapi.eastmoney.com/api/suggest/get?input={encoded}&type=14&token=D43BF722C8E33BDC906FB84D85E326E8"
            resp = _req.get(search_url, timeout=5)
            data = resp.json()
            items = data.get("QuotationCodeTable", {}).get("Data", [])
            a_stocks = [i for i in items if i.get("Classify") == "AStock" and i["Code"] == code]
            if a_stocks:
                name = a_stocks[0]["Name"]
        except Exception:
            pass
    
    # 获取K线数据 - 用东方财富API（毫秒级）
    try:
        # 确定市场前缀：0=深市 1=沪市
        market = "1" if code.startswith(("6", "9")) else "0"
        secid = f"{market}.{code}"
        
        import requests as _req
        market = "1" if code.startswith(("6", "9")) else "0"
        secid = f"{market}.{code}"
        kline_url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1&beg=20250101&end=20261231"
        resp = _req.get(kline_url, timeout=10)
        kdata = resp.json()
        
        raw_klines = kdata.get("data", {}).get("klines", [])
        if len(raw_klines) < 60:
            return {"error": f"股票 {code} 数据不足60根K线"}
        
        klines = []
        for line in raw_klines[-120:]:
            parts = line.split(",")
            # 日期,开盘,收盘,最高,最低,成交量,成交额
            klines.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
            })
        
        # 跑缠论+技术指标+综合评分
        chanlun = full_analysis(klines)
        tech = full_technical_analysis(klines, chanlun)
        
        # 当前价格信息
        latest = klines[-1]
        prev = klines[-2] if len(klines) >= 2 else latest
        
        # 涨跌幅
        pct_today = round((latest["close"] - prev["close"]) / prev["close"] * 100, 2)
        pct_5d = round((latest["close"] - klines[-5]["close"]) / klines[-5]["close"] * 100, 2)
        pct_20d = round((latest["close"] - klines[-20]["close"]) / klines[-20]["close"] * 100, 2) if len(klines) >= 20 else None
        
        # 检查是否在wu2198股票池中
        in_pool = False
        pool_info = {}
        try:
            master_path = "/vol1/1000/openzl/stock-research/stock_pool/wu2198_master_stock_pool.json"
            with open(master_path) as f:
                pool = json.load(f)
            rows = pool.get("rows", pool) if isinstance(pool, dict) else pool
            if isinstance(rows, dict): rows = rows.get("rows", [])
            for s in rows:
                if str(s.get("stock_code","")) == code or s.get("stock_name","") == name:
                    in_pool = True
                    pool_info = {"score": s.get("live_score",0), "bucket": s.get("live_bucket",""), "sector": s.get("sector","")}
                    break
        except Exception:
            pass
        
        return {
            "name": name,
            "code": code,
            "current_price": latest["close"],
            "current_date": latest["date"],
            "pct_today": pct_today,
            "pct_5d": pct_5d,
            "pct_20d": pct_20d,
            "in_wu2198_pool": in_pool,
            "pool_info": pool_info if in_pool else None,
            "chanlun": chanlun.get("summary", {}),
            "chanlun_signals": chanlun.get("buy_sell_points", []),
            "chanlun_patterns": chanlun.get("patterns", []),
            "zhongshu": chanlun.get("zhongshu", []),
            "recent_bi": chanlun.get("recent_bi", []),
            "recent_fractals": chanlun.get("recent_fractals", []),
            "rsi": tech.get("rsi", {}),
            "boll": tech.get("boll", {}),
            "ma": tech.get("ma", {}),
            "kdj": tech.get("kdj", {}),
            "volume": tech.get("volume", {}),
            "gaps": tech.get("gaps", []),
            "multi_timeframe": tech.get("multi_timeframe", {}),
            "composite_score": tech.get("composite_score", {}),
            # wu2198视角评价
            "wu_eval": evaluate_stock_with_wu(
                name or "", code, in_pool,
                pool_info.get("sector", "") if in_pool else "",
                tech.get("composite_score", {}).get("score", 0),
                tech.get("composite_score", {}).get("verdict", ""),
                pool_info if in_pool else None,
            ),
        }
    except Exception as e:
        return {"error": f"分析失败: {e}"}


@app.get("/api/daily-strategy")
async def api_daily_strategy():
    """每日策略报告 - 以wu2198观点为核心的融合策略"""
    try:
        # 上证指数数据
        sh_path = BASE_DIR / "data" / "sh000001.csv"
        cyb_path = BASE_DIR / "data" / "sz399006.csv"
        
        if not sh_path.exists() or not cyb_path.exists():
            return {"error": "指数数据不存在，请先运行daily_update.py"}
        
        df_sh = pd.read_csv(sh_path)
        df_cyb = pd.read_csv(cyb_path)
        
        sh_price = float(df_sh.iloc[-1]["close"])
        cyb_price = float(df_cyb.iloc[-1]["close"])
        
        # 计算上证技术评分
        klines_sh = []
        for _, r in df_sh.tail(120).iterrows():
            klines_sh.append({
                "date": str(r["date"]), "open": float(r["open"]),
                "high": float(r["high"]), "low": float(r["low"]),
                "close": float(r["close"]), "volume": float(r.get("volume", 0)),
            })
        chanlun = full_analysis(klines_sh)
        tech = full_technical_analysis(klines_sh, chanlun)
        tech_score = tech.get("composite_score", {}).get("score", 0)
        tech_verdict = tech.get("composite_score", {}).get("verdict", "")
        
        strategy = daily_strategy(sh_price, cyb_price, tech_score, tech_verdict)
        return strategy
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/weibo-latest")
async def api_weibo_latest(limit: int = 20):
    """wu2198最新微博 - 从本地缓存读取"""
    try:
        posts = []
        path = BASE_DIR / "data" / "wu2198_latest.json"
        if path.exists() and path.stat().st_size > 5:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                posts = raw
            elif isinstance(raw, dict):
                posts = raw.get("posts") or raw.get("items") or raw.get("data") or []
                if not posts and raw.get("text"):
                    posts = [raw]
        # fallback: vip + message pools texts
        if not posts:
            vip = _load_json(VIP_MESSAGES, [])
            if isinstance(vip, dict):
                vip = vip.get("messages") or vip.get("items") or []
            for v in vip[:limit]:
                posts.append({
                    "date": v.get("created_ts") or v.get("date") or "",
                    "text": v.get("text") or v.get("content") or "",
                    "vip": True,
                    "source": "vip",
                })
        if not posts:
            live = _load_json(LIVE_POOL, {})
            for mp in (live.get("message_pools") or [])[:limit]:
                posts.append({
                    "date": mp.get("created_at") or mp.get("date") or live.get("generated_at") or "",
                    "text": mp.get("text") or mp.get("summary") or mp.get("title") or "",
                    "source": "live_pool",
                    "stocks": mp.get("stocks") or [],
                })
        posts = [p for p in posts if (p.get("text") or p.get("content"))]
        return {"count": len(posts[:limit]), "posts": posts[:limit]}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/wu-viewpoints")
async def api_wu_viewpoints():
    """wu2198最新观点库 - 板块态度+关键点位"""
    return WU_VIEWPOINTS


@app.get("/api/wave-analysis")
async def api_wave_analysis():
    """wu2198 波浪理论分析 - 上证指数浪型标注与走势预测"""
    csv_path = BASE_DIR / "data" / "sh000001.csv"
    current_price = None
    kline_data = []

    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path)
            current_price = float(df['close'].iloc[-1])
            # Last 500 days kline for chart (covers full wave cycle from 2024-09)
            recent = df.tail(500)
            for _, r in recent.iterrows():
                kline_data.append({
                    "date": str(r['date']),
                    "open": float(r['open']),
                    "high": float(r['high']),
                    "low": float(r['low']),
                    "close": float(r['close']),
                })
        except Exception:
            pass

    analysis = get_analysis(current_price)
    analysis["kline"] = kline_data
    
    # 上证指数技术点位标注
    sh_levels = analysis.get("sh_key_levels", {})
    if current_price and sh_levels:
        resistance = sh_levels.get("resistance", 4132)
        target = sh_levels.get("break_4070_target", 4031)
        turn_down = sh_levels.get("turn_down_from", 4175)
        
        if current_price > resistance:
            sh_zone = f"反压{resistance}之上，需突破确认"
        elif current_price > 4070:
            sh_zone = f"反压{resistance}之下，破4070看{target}"
        elif current_price > target:
            sh_zone = f"⚠️ 已破4070，第一步看{target}"
        else:
            sh_zone = f"🔴 已破{target}，技术面进一步走弱"
        
        analysis["sh_analysis"] = {
            "current": current_price,
            "turn_down_from": turn_down,
            "resistance": resistance,
            "break_4070_target": target,
            "zone": sh_zone,
            "status": sh_levels.get("current_status", ""),
        }
    
    # 创业板指数K线 + 关键点位
    cyb_csv = BASE_DIR / "data" / "sz399006.csv"
    cyb_kline = []
    cyb_price = None
    if cyb_csv.exists():
        try:
            df2 = pd.read_csv(cyb_csv)
            cyb_price = float(df2['close'].iloc[-1])
            recent2 = df2.tail(500)
            for _, r in recent2.iterrows():
                cyb_kline.append({
                    "date": str(r['date']),
                    "open": float(r['open']),
                    "high": float(r['high']),
                    "low": float(r['low']),
                    "close": float(r['close']),
                })
        except Exception:
            pass
    
    analysis["cyb_kline"] = cyb_kline
    analysis["cyb_current_price"] = cyb_price
    
    # 创业板分析
    if cyb_price:
        cyb = analysis.get("cyb_key_levels", {})
        short_pivot = cyb.get("short_term_pivot", 4150)
        medium_pivot = cyb.get("medium_term_pivot", 3750)
        m_head_risk = cyb.get("m_head_risk", True)
        
        if cyb_price > short_pivot:
            cyb_zone = f"短线{short_pivot}之上，波段趋势维持"
        elif cyb_price > medium_pivot:
            cyb_zone = f"⚠️ 已破短线{short_pivot}" + (", 警惕小M头" if m_head_risk else "") + f", 关注中线{medium_pivot}支撑"
        else:
            cyb_zone = f"🔴 破中线{medium_pivot}，趋势转弱"
        
        analysis["cyb_analysis"] = {
            "current": cyb_price,
            "short_pivot": short_pivot,
            "medium_pivot": medium_pivot,
            "above_short": cyb_price > short_pivot,
            "above_medium": cyb_price > medium_pivot,
            "m_head_risk": m_head_risk,
            "zone": cyb_zone,
            "strategy": cyb.get("current_strategy", ""),
            "near_medium_support": abs(cyb_price - medium_pivot) / medium_pivot < 0.02,
            "note": f"6月11日最低3756点，几乎精准测试3750中线支撑",
        }
    
    return analysis


@app.get("/api/chanlun")
async def api_chanlun(index: str = "sh"):
    """缠论技术分析 - 分型/笔/中枢/买卖点/形态"""
    csv_name = "sh000001.csv" if index == "sh" else "sz399006.csv"
    csv_path = BASE_DIR / "data" / csv_name
    
    if not csv_path.exists():
        return {"error": f"数据文件 {csv_name} 不存在"}
    
    try:
        df = pd.read_csv(csv_path)
        klines = []
        for _, r in df.tail(120).iterrows():
            klines.append({
                "date": str(r["date"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
            })
        result = full_analysis(klines)
        result["index_name"] = "上证指数" if index == "sh" else "创业板指数"
        # Normalize summary to object expected by frontend, keep text aliases
        pos = result.get("position") or result.get("summary") or ""
        if not isinstance(result.get("summary"), dict):
            result["summary_text"] = str(result.get("summary") or pos)
            result["summary"] = {
                "current_price": result.get("current_price"),
                "current_direction": (result.get("recent_bi") or [{}])[-1].get("direction", "down")
                if result.get("recent_bi")
                else "down",
                "macd_status": (result.get("macd") or {}).get("status", "-"),
                "position_in_zhongshu": pos if isinstance(pos, str) else str(pos),
            }
        # Normalize buy/sell point fields
        norm_bs = []
        for p in result.get("buy_sell_points") or []:
            if not isinstance(p, dict):
                continue
            kind = p.get("kind") or p.get("type") or ""
            if "买" in str(kind) and "buy" not in str(kind).lower():
                kind_key = "buy_" + str(kind)
            elif "卖" in str(kind) and "sell" not in str(kind).lower():
                kind_key = "sell_" + str(kind)
            else:
                kind_key = str(kind)
            norm_bs.append(
                {
                    "kind": kind_key,
                    "type": p.get("type") or kind,
                    "date": p.get("date"),
                    "price": p.get("price"),
                    "confidence": p.get("confidence", 0.6),
                    "description": p.get("description") or p.get("note") or "",
                }
            )
        result["buy_sell_points"] = norm_bs
        # patterns: add bearish flag
        norm_pat = []
        for p in result.get("patterns") or []:
            if not isinstance(p, dict):
                continue
            name = p.get("name") or ""
            bearish = p.get("bearish")
            if bearish is None:
                bearish = any(x in name for x in ["M头", "头肩顶", "顶背驰", "下跌"])
                if p.get("status") == "已突破" and any(x in name for x in ["M头", "头肩顶"]):
                    bearish = False
            norm_pat.append({**p, "bearish": bool(bearish), "target": p.get("target")})
        result["patterns"] = norm_pat
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/indicators")
async def api_indicators(index: str = "sh"):
    """综合技术指标分析 - RSI/布林/均线/KDJ/量价/多周期/综合评分"""
    csv_name = "sh000001.csv" if index == "sh" else "sz399006.csv"
    csv_path = BASE_DIR / "data" / csv_name
    
    if not csv_path.exists():
        return {"error": f"数据文件 {csv_name} 不存在"}
    
    try:
        df = pd.read_csv(csv_path)
        klines = []
        for _, r in df.tail(120).iterrows():
            klines.append({
                "date": str(r["date"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume", 0)),
            })
        
        # 先跑缠论（综合评分需要）
        chanlun = full_analysis(klines)
        result = full_technical_analysis(klines, chanlun)
        result["index_name"] = "上证指数" if index == "sh" else "创业板指数"

        # Flatten → nested adapters for dashboard frontend
        rsi_v = result.get("rsi")
        if not isinstance(rsi_v, dict):
            try:
                rv = float(rsi_v)
            except Exception:
                rv = None
            zone = "中性"
            if rv is not None:
                if rv >= 70:
                    zone = "超买"
                elif rv <= 30:
                    zone = "超卖偏多"
                elif rv >= 55:
                    zone = "偏多"
                elif rv <= 45:
                    zone = "偏空"
            result["rsi"] = {"value": rv, "zone": zone, "divergence": ""}

        boll = result.get("boll")
        if isinstance(boll, dict) and "position" not in boll:
            mid = boll.get("mid")
            upper = boll.get("upper")
            lower = boll.get("lower")
            close = klines[-1]["close"] if klines else None
            pos = "中轨附近"
            if close is not None and mid and upper and lower:
                if close >= upper:
                    pos = "上轨附近偏多"
                elif close <= lower:
                    pos = "下轨附近偏空"
                elif close > mid:
                    pos = "中轨上方"
                else:
                    pos = "中轨下方"
            width = None
            try:
                width = (float(upper) - float(lower)) / float(mid) if mid else None
            except Exception:
                width = None
            boll = {**boll, "position": pos, "squeeze": f"带宽{width:.2%}" if width is not None else ""}
            result["boll"] = boll

        if "ma" not in result or not isinstance(result.get("ma"), dict):
            ma5 = result.get("ma5")
            ma20 = result.get("ma20")
            ma60 = result.get("ma60")
            close = klines[-1]["close"] if klines else None
            arr = "均线缠绕"
            try:
                if ma5 and ma20 and ma60 and ma5 > ma20 > ma60:
                    arr = "多头排列"
                elif ma5 and ma20 and ma60 and ma5 < ma20 < ma60:
                    arr = "空头排列"
            except Exception:
                pass
            cross = ""
            try:
                if close and ma5:
                    cross = "站上MA5" if close >= ma5 else "跌破MA5"
            except Exception:
                pass
            life = ""
            try:
                if close and ma20:
                    life = "生命线上方" if close >= ma20 else "生命线下方"
            except Exception:
                pass
            result["ma"] = {
                "arrangement": arr,
                "cross": cross,
                "life_line": life,
                "values": {"ma5": ma5, "ma20": ma20, "ma60": ma60},
            }

        kdj = result.get("kdj")
        if isinstance(kdj, dict) and "zone" not in kdj:
            j = kdj.get("j")
            zone = "中性"
            try:
                if j is not None and float(j) >= 80:
                    zone = "超买"
                elif j is not None and float(j) <= 20:
                    zone = "超卖"
            except Exception:
                pass
            result["kdj"] = {**kdj, "zone": zone, "cross": "", "j_signal": ""}

        if "volume" not in result:
            result["volume"] = {"vol_vs_avg20": "-", "divergence": "正常"}
        if "multi_timeframe" not in result:
            result["multi_timeframe"] = {
                "resonance": "日线为主",
                "daily": {"trend": result.get("verdict") or "-"},
                "weekly": {"trend": "-"},
                "monthly": {"trend": "-"},
            }
        if "composite_score" not in result:
            score = result.get("score")
            try:
                score_f = float(score)
            except Exception:
                score_f = 0.0
            votes = result.get("details") or [["综合评分", score_f]]
            if not votes:
                votes = [["综合评分", score_f]]
            norm_votes = []
            for v in votes:
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    try:
                        norm_votes.append([str(v[0]), float(v[1])])
                    except Exception:
                        norm_votes.append([str(v[0]), 0.0])
                elif isinstance(v, dict):
                    norm_votes.append(
                        [
                            str(v.get("name") or v.get("item") or "项"),
                            float(v.get("score") or v.get("value") or 0),
                        ]
                    )
            if not norm_votes:
                norm_votes = [["综合评分", score_f]]
            result["composite_score"] = {
                "score": score_f,
                "verdict": result.get("verdict") or result.get("summary") or "",
                "bull": max(0, int(round(max(score_f, 0) * 2))),
                "bear": max(0, int(round(max(-score_f, 0) * 2))),
                "votes": norm_votes,
            }
        return result
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    uvicorn.run(app, host="0.0.0.0", port=port)


