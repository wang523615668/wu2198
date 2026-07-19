#!/usr/bin/env python3
"""wu2198 波浪理论分析 - 上证指数浪型标注与预测（恢复版最小可用实现）"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"

# wu2198 关键关键位（可被最新观点覆盖）
SH_KEY_LEVELS = {
    "resistance": 4120,
    "support": 4050,
    "key_level": 4070,
    "break_4070_target": 4050,
    "triangle_expected": 3987,
}

# 历史波浪框架（粗粒度）
WAVES = [
    {"name": "W1", "start_date": "2024-09-18", "start_price": 2689, "end_date": "2024-10-08", "end_price": 3674, "color": "#3fb950"},
    {"name": "W2", "start_date": "2024-10-08", "start_price": 3674, "end_date": "2025-01-13", "end_price": 3040, "color": "#f85149"},
    {"name": "W3", "start_date": "2025-01-13", "start_price": 3040, "end_date": "2025-10-08", "end_price": 3900, "color": "#58a6ff"},
    {"name": "W4", "start_date": "2025-10-08", "start_price": 3900, "end_date": "2026-04-07", "end_price": 3500, "color": "#d29922"},
]


def _load_csv(name: str):
    import pandas as pd
    p = DATA_DIR / name
    if not p.exists():
        return None
    df = pd.read_csv(p)
    # normalize columns
    colmap = {}
    for c in df.columns:
        cl = str(c).lower()
        if c in ("日期", "date") or cl == "date":
            colmap[c] = "date"
        elif c in ("开盘", "open") or cl == "open":
            colmap[c] = "open"
        elif c in ("收盘", "close") or cl == "close":
            colmap[c] = "close"
        elif c in ("最高", "high") or cl == "high":
            colmap[c] = "high"
        elif c in ("最低", "low") or cl == "low":
            colmap[c] = "low"
        elif c in ("成交量", "volume") or cl == "volume":
            colmap[c] = "volume"
    df = df.rename(columns=colmap)
    if "date" in df.columns:
        df["date"] = df["date"].astype(str)
    return df


def _df_to_klines(df, tail: int = 500) -> list[dict]:
    if df is None or df.empty:
        return []
    src = df.tail(tail)
    out = []
    for _, r in src.iterrows():
        out.append({
            "date": str(r.get("date", "")),
            "open": float(r.get("open", 0) or 0),
            "close": float(r.get("close", 0) or 0),
            "high": float(r.get("high", 0) or 0),
            "low": float(r.get("low", 0) or 0),
            "volume": float(r.get("volume", 0) or 0),
        })
    return out


def get_analysis(current_price: float | None = None, index: str = "sh") -> dict[str, Any]:
    name = "sh000001.csv" if index in ("sh", "sse", "000001") else "sz399006.csv"
    df = _load_csv(name)
    kline = _df_to_klines(df, 500)
    if current_price is None and kline:
        current_price = float(kline[-1]["close"])
    current_price = float(current_price or 0)
    levels = dict(SH_KEY_LEVELS)
    bias = "中性"
    if current_price >= levels["resistance"]:
        bias = "偏多"
    elif current_price >= levels["key_level"]:
        bias = "中性偏多"
    elif current_price >= levels["support"]:
        bias = "偏空调整"
    else:
        bias = "偏空"
    return {
        "index": index,
        "current_price": current_price,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sh_key_levels": levels,
        "bias": bias,
        "waves": WAVES,
        "kline": kline,
        "summary": f"现价{current_price:.0f}，关键位{levels['key_level']}，阻力{levels['resistance']}，支撑{levels['support']}，判断：{bias}",
    }
