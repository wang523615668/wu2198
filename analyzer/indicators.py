#!/usr/bin/env python3
"""扩展技术指标引擎（恢复版）"""
from __future__ import annotations
from typing import Any


def calc_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        out[period] = 100.0 if avg_gain > 0 else 50.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100 - 100 / (1 + rs)
    for i in range(period + 1, n):
        d = closes[i] - closes[i - 1]
        gain = max(d, 0.0)
        loss = max(-d, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[i] = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100 - 100 / (1 + rs)
    return out


def calc_ma(closes: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    s = 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= period:
            s -= closes[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def calc_boll(closes: list[float], period: int = 20, k: float = 2.0):
    mid = calc_ma(closes, period)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is None:
            continue
        window = closes[i - period + 1:i + 1]
        mean = mid[i]
        var = sum((x - mean) ** 2 for x in window) / period
        std = var ** 0.5
        upper[i] = mean + k * std
        lower[i] = mean - k * std
    return mid, upper, lower


def calc_kdj(highs, lows, closes, n: int = 9, m1: int = 3, m2: int = 3):
    k_list: list[float | None] = [None] * len(closes)
    d_list: list[float | None] = [None] * len(closes)
    j_list: list[float | None] = [None] * len(closes)
    k = 50.0
    d = 50.0
    for i in range(len(closes)):
        if i < n - 1:
            continue
        hh = max(highs[i - n + 1:i + 1])
        ll = min(lows[i - n + 1:i + 1])
        rsv = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100
        k = (m1 - 1) / m1 * k + 1 / m1 * rsv
        d = (m2 - 1) / m2 * d + 1 / m2 * k
        j = 3 * k - 2 * d
        k_list[i], d_list[i], j_list[i] = k, d, j
    return k_list, d_list, j_list


def composite_score(rsi_v, ma_bias, kdj_j, boll_pos, volume_bias=0.0) -> dict[str, Any]:
    score = 0.0
    details = []
    if rsi_v is not None:
        if rsi_v < 30:
            score += 1.5; details.append("RSI超卖")
        elif rsi_v > 70:
            score -= 1.5; details.append("RSI超买")
        elif rsi_v < 45:
            score += 0.5
        elif rsi_v > 55:
            score -= 0.5
    score += ma_bias
    if kdj_j is not None:
        if kdj_j < 20:
            score += 1.0; details.append("KDJ超卖")
        elif kdj_j > 80:
            score -= 1.0; details.append("KDJ超买")
    score += boll_pos
    score += volume_bias
    if score >= 3:
        verdict = "强烈看多🐂🐂🐂"
    elif score >= 1.5:
        verdict = "偏多🐂"
    elif score >= 0:
        verdict = "中性观望😐"
    elif score >= -1.5:
        verdict = "偏空🐻"
    else:
        verdict = "强烈看空🐻🐻🐻"
    return {"score": round(score, 2), "verdict": verdict, "details": details}


def full_technical_analysis(klines: list[dict] | None = None, chanlun=None, closes=None, highs=None, lows=None, volumes=None) -> dict[str, Any]:
    if klines:
        closes = [float(k["close"]) for k in klines]
        highs = [float(k["high"]) for k in klines]
        lows = [float(k["low"]) for k in klines]
        volumes = [float(k.get("volume", 0) or 0) for k in klines]
    closes = list(closes or [])
    highs = list(highs or closes)
    lows = list(lows or closes)
    volumes = list(volumes or [0] * len(closes))
    if len(closes) < 30:
        return {"error": "not_enough_data", "score": 0, "verdict": "中性观望😐", "rsi": None}

    rsi = calc_rsi(closes)
    ma5 = calc_ma(closes, 5)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)
    mid, upper, lower = calc_boll(closes)
    k, d, j = calc_kdj(highs, lows, closes)

    i = len(closes) - 1
    c = closes[i]
    ma_bias = 0.0
    if ma5[i] and ma20[i]:
        if c > ma5[i] > ma20[i]:
            ma_bias += 1.0
        elif c < ma5[i] < ma20[i]:
            ma_bias -= 1.0
    if ma60[i]:
        ma_bias += 0.5 if c > ma60[i] else -0.5

    boll_pos = 0.0
    if upper[i] and lower[i] and mid[i]:
        if c <= lower[i]:
            boll_pos = 1.0
        elif c >= upper[i]:
            boll_pos = -1.0
        elif c < mid[i]:
            boll_pos = 0.3
        else:
            boll_pos = -0.3

    vol_bias = 0.0
    if i >= 5:
        avg = sum(volumes[i-5:i]) / 5 or 1
        if volumes[i] > avg * 1.5 and c > closes[i-1]:
            vol_bias = 0.5
        elif volumes[i] > avg * 1.5 and c < closes[i-1]:
            vol_bias = -0.5

    comp = composite_score(rsi[i], ma_bias, j[i], boll_pos, vol_bias)
    if isinstance(chanlun, dict):
        pos = str(chanlun.get("position") or chanlun.get("summary") or "")
        if "偏多" in pos: comp["score"] = round(comp["score"] + 0.3, 2)
        if "偏空" in pos: comp["score"] = round(comp["score"] - 0.3, 2)
    return {
        "rsi": round(rsi[i], 2) if rsi[i] is not None else None,
        "ma5": round(ma5[i], 2) if ma5[i] else None,
        "ma20": round(ma20[i], 2) if ma20[i] else None,
        "ma60": round(ma60[i], 2) if ma60[i] else None,
        "boll": {
            "mid": round(mid[i], 2) if mid[i] else None,
            "upper": round(upper[i], 2) if upper[i] else None,
            "lower": round(lower[i], 2) if lower[i] else None,
        },
        "kdj": {
            "k": round(k[i], 2) if k[i] is not None else None,
            "d": round(d[i], 2) if d[i] is not None else None,
            "j": round(j[i], 2) if j[i] is not None else None,
        },
        "score": comp["score"],
        "verdict": comp["verdict"],
        "details": comp["details"],
        "summary": f"{comp['verdict']} score={comp['score']}",
        "chanlun": (chanlun or {}),
    }
