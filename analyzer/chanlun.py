#!/usr/bin/env python3
"""缠论 + 经典技术分析引擎（恢复版可用实现）"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Fractal:
    idx: int
    kind: str  # top/bottom
    price: float
    date: str


def _ema(vals: list[float], period: int) -> list[float]:
    out = []
    k = 2 / (period + 1)
    e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def calc_macd(closes: list[float]):
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    bar = [(a - b) * 2 for a, b in zip(dif, dea)]
    return dif, dea, bar


def detect_fractals(highs, lows, dates) -> list[Fractal]:
    fr: list[Fractal] = []
    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1] and lows[i] > lows[i-1] and lows[i] > lows[i+1]:
            fr.append(Fractal(i, "top", highs[i], dates[i]))
        elif lows[i] < lows[i-1] and lows[i] < lows[i+1] and highs[i] < highs[i-1] and highs[i] < highs[i+1]:
            fr.append(Fractal(i, "bottom", lows[i], dates[i]))
    # merge same type
    merged: list[Fractal] = []
    for f in fr:
        if not merged:
            merged.append(f); continue
        last = merged[-1]
        if f.kind == last.kind:
            if f.kind == "top" and f.price >= last.price:
                merged[-1] = f
            elif f.kind == "bottom" and f.price <= last.price:
                merged[-1] = f
        else:
            if f.idx - last.idx >= 4:
                merged.append(f)
            else:
                # too close: keep extreme
                if f.kind == "top" and f.price > last.price:
                    merged[-1] = f
                elif f.kind == "bottom" and f.price < last.price:
                    merged[-1] = f
    return merged


def build_bi(fractals: list[Fractal]) -> list[dict]:
    bis = []
    for a, b in zip(fractals, fractals[1:]):
        if a.kind == b.kind:
            continue
        direction = "up" if a.kind == "bottom" else "down"
        bis.append({
            "start_idx": a.idx, "end_idx": b.idx,
            "start_date": a.date, "end_date": b.date,
            "start_price": a.price, "end_price": b.price,
            "direction": direction,
            "high": max(a.price, b.price),
            "low": min(a.price, b.price),
        })
    return bis


def build_zhongshu(bis: list[dict], max_extend: int = 20) -> list[dict]:
    zs = []
    i = 0
    while i + 2 < len(bis):
        window = bis[i:i+3]
        highs = [b["high"] for b in window]
        lows = [b["low"] for b in window]
        zg = min(highs)
        zd = max(lows)
        if zd >= zg:
            i += 1
            continue
        end = i + 2
        ext = 0
        while end + 1 < len(bis) and ext < max_extend:
            nb = bis[end + 1]
            if nb["low"] <= zg and nb["high"] >= zd:
                end += 1
                ext += 1
                highs.append(nb["high"]); lows.append(nb["low"])
                zg = min(highs); zd = max(lows)
                if zd >= zg:
                    break
            else:
                break
        if zd < zg:
            zs.append({
                "start_date": bis[i]["start_date"],
                "end_date": bis[end]["end_date"],
                "zg": zg, "zd": zd,
                "gg": max(highs), "dd": min(lows),
                "bi_count": end - i + 1,
            })
        i = end + 1
    return zs


def detect_patterns(bis: list[dict], current_price: float) -> list[dict]:
    patterns = []
    tops = [b for b in bis if b["direction"] == "up"]
    bottoms = [b for b in bis if b["direction"] == "down"]
    # double top rough
    if len(tops) >= 2:
        a, b = tops[-2], tops[-1]
        if abs(a["end_price"] - b["end_price"]) / max(a["end_price"], 1) < 0.02:
            neck = min(a["low"], b["low"])
            status = "形成中"
            if current_price > max(a["end_price"], b["end_price"]):
                status = "已突破"
            patterns.append({
                "name": "M头",
                "status": status,
                "neckline": neck,
                "target": neck - (max(a["end_price"], b["end_price"]) - neck),
                "peaks": [a["end_price"], b["end_price"]],
            })
    if len(bottoms) >= 2:
        a, b = bottoms[-2], bottoms[-1]
        if abs(a["end_price"] - b["end_price"]) / max(a["end_price"], 1) < 0.02:
            neck = max(a["high"], b["high"])
            status = "形成中"
            if current_price < min(a["end_price"], b["end_price"]):
                status = "已跌破"
            patterns.append({
                "name": "W底",
                "status": status,
                "neckline": neck,
                "target": neck + (neck - min(a["end_price"], b["end_price"])),
                "troughs": [a["end_price"], b["end_price"]],
            })
    return patterns


def buy_sell_points(bis: list[dict], zs: list[dict], macd_bar: list[float], dates: list[str]) -> list[dict]:
    points = []
    if not zs or len(bis) < 3:
        return points
    last_zs = zs[-1]
    # simple class-3 style around last zhongshu
    last_bi = bis[-1]
    if last_bi["direction"] == "up" and last_bi["end_price"] > last_zs["zg"]:
        points.append({
            "type": "三类买点候选",
            "date": last_bi["end_date"],
            "price": last_bi["end_price"],
            "note": f"突破中枢ZG={last_zs['zg']:.0f}",
        })
    if last_bi["direction"] == "down" and last_bi["end_price"] < last_zs["zd"]:
        points.append({
            "type": "三类卖点候选",
            "date": last_bi["end_date"],
            "price": last_bi["end_price"],
            "note": f"跌破中枢ZD={last_zs['zd']:.0f}",
        })
    # divergence on last two same-direction bi
    for i in range(len(bis) - 3, -1, -1):
        b1, b2 = bis[i], bis[i + 2]
        if b1["direction"] != b2["direction"]:
            continue
        a1 = sum(abs(macd_bar[j]) for j in range(b1["start_idx"], min(b1["end_idx"] + 1, len(macd_bar))))
        a2 = sum(abs(macd_bar[j]) for j in range(b2["start_idx"], min(b2["end_idx"] + 1, len(macd_bar))))
        if a1 <= 0:
            continue
        if b2["direction"] == "down" and b2["end_price"] < b1["end_price"] and a2 < a1 * 0.7:
            points.append({"type": "一类买点(底背驰)", "date": b2["end_date"], "price": b2["end_price"], "note": f"MACD面积比{a2/a1:.2f}"})
            break
        if b2["direction"] == "up" and b2["end_price"] > b1["end_price"] and a2 < a1 * 0.7:
            points.append({"type": "一类卖点(顶背驰)", "date": b2["end_date"], "price": b2["end_price"], "note": f"MACD面积比{a2/a1:.2f}"})
            break
    return points


def full_analysis(klines: list[dict] | None = None, opens=None, highs=None, lows=None, closes=None, dates=None) -> dict[str, Any]:
    if klines:
        dates = [str(k.get("date", i)) for i, k in enumerate(klines)]
        highs = [float(k["high"]) for k in klines]
        lows = [float(k["low"]) for k in klines]
        closes = [float(k["close"]) for k in klines]
    dates = [str(d) for d in (dates or list(range(len(closes or []))))]
    highs = list(highs or [])
    lows = list(lows or [])
    closes = list(closes or [])
    if len(closes) < 30:
        return {"error": "not_enough_data", "summary": "数据不足", "fractals": [], "bi": [], "zhongshu": [], "buy_sell_points": [], "patterns": []}

    fr = detect_fractals(highs, lows, dates)
    bis = build_bi(fr)
    zs = build_zhongshu(bis)
    dif, dea, bar = calc_macd(closes)
    price = closes[-1]
    patterns = detect_patterns(bis, price)
    points = buy_sell_points(bis, zs, bar, dates)

    if zs:
        last = zs[-1]
        if price > last["zg"]:
            pos = "中枢上方，偏多"
        elif price < last["zd"]:
            pos = "中枢下方，偏空"
        else:
            pos = "中枢内，震荡"
    else:
        pos = "无明确中枢"

    # invalidate bearish patterns if price above neckline
    for p in patterns:
        if p["name"] in ("M头", "头肩顶") and price > p.get("neckline", price):
            p["status"] = "已突破"

    return {
        "summary": pos,
        "position": pos,
        "current_price": price,
        "recent_fractals": [{"date": f.date, "kind": f.kind, "price": f.price} for f in fr[-12:]],
        "recent_bi": bis[-12:],
        "zhongshu": zs[-5:],
        "buy_sell_points": points,
        "patterns": patterns,
        "macd": {
            "dif": round(dif[-1], 3),
            "dea": round(dea[-1], 3),
            "bar": round(bar[-1], 3),
            "status": "多头" if dif[-1] > dea[-1] else "空头",
        },
    }
