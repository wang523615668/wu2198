#!/usr/bin/env python3
"""每日收盘自动更新脚本：获取指数数据 → 技术分析 → 生成简报 → 条件推送"""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

# ── 路径 ──
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
SH_PATH = DATA / "sh000001.csv"
SZ_PATH = DATA / "sz399006.csv"
REPORT_PATH = DATA / "daily_report.json"

SYMBOLS = {
    "上证指数": {"symbol": "sh000001", "path": SH_PATH},
    "创业板指": {"symbol": "sz399006", "path": SZ_PATH},
}


def step_a_fetch_index(name: str, symbol: str, out_path: Path) -> pd.DataFrame:
    """a) 用东财 K 线获取指数日线，筛选 >=2024-01-01，保存 CSV（不用 akshare）"""
    import urllib.parse
    import urllib.request

    # 东财指数 secid：上证 1.000001，创业板 0.399006
    secid_map = {
        "sh000001": "1.000001",
        "sz399006": "0.399006",
    }
    secid = secid_map.get(symbol)
    if not secid:
        raise ValueError(f"unsupported symbol for eastmoney: {symbol}")

    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": "101",
        "fqt": "1",
        "beg": "20240101",
        "end": "20500101",
    }
    url = "http://push2his.eastmoney.com/api/qt/stock/kline/get?" + urllib.parse.urlencode(params)
    print(f"[{name}] 正在获取 {symbol} via eastmoney ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    raw = ((payload.get("data") or {}).get("klines") or [])
    rows = []
    for line in raw:
        # date,open,close,high,low,volume,amount
        parts = str(line).split(",")
        if len(parts) < 6:
            continue
        rows.append({
            "date": parts[0][:10],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": float(parts[5]),
            "amount": float(parts[6]) if len(parts) > 6 and parts[6] not in ("", "-") else 0.0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"eastmoney returned empty klines for {symbol}")
    df = df[df["date"] >= "2024-01-01"].reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"[{name}] 已保存 {len(df)} 条记录到 {out_path}")
    return df


def step_b_fetch_sz() -> pd.DataFrame:
    return step_a_fetch_index("创业板指", "sz399006", SZ_PATH)


def step_c_technical_analysis(df: pd.DataFrame) -> dict:
    """c) 调用 indicators.full_technical_analysis 计算上证综合评分（适配恢复版返回结构）"""
    from indicators import full_technical_analysis

    klines = df.to_dict("records")
    result = full_technical_analysis(klines)
    # 兼容旧/新两种返回结构
    if "composite_score" in result:
        score = result["composite_score"].get("score")
        verdict = result["composite_score"].get("verdict")
        price = result.get("current_price")
    else:
        score = result.get("score")
        verdict = result.get("verdict")
        # 从 df 补收盘价/日期
        price = float(df.iloc[-1]["close"]) if len(df) else None
        result.setdefault("current_price", price)
        result.setdefault("current_date", str(df.iloc[-1]["date"]) if len(df) else None)
        result["composite_score"] = {
            "score": score,
            "verdict": verdict,
            "bull": None,
            "bear": None,
            "details": result.get("details") or [],
        }
        # flatten helpers for report builder
        rsi_v = result.get("rsi")
        result["rsi"] = {"value": rsi_v, "zone": ("超买" if (rsi_v or 0) >= 70 else "超卖" if (rsi_v or 100) <= 30 else "中性")}
        result["ma"] = {
            "arrangement": f"MA5={result.get('ma5')} / MA20={result.get('ma20')} / MA60={result.get('ma60')}",
            "cross": "-",
        }
        boll = result.get("boll") or {}
        result["boll"] = {
            **boll,
            "position": "中轨附近",
            "squeeze": "-",
        }
        kdj = result.get("kdj") or {}
        result["kdj"] = {**kdj, "zone": "-", "cross": "-"}
        result["volume"] = {"vol_vs_avg20": "-", "divergence": None}
        result["multi_timeframe"] = {"resonance": "-"}
        result["gaps"] = []
    print(f"[技术分析] 评分={score}, 判定={verdict}, 收盘价={price}")
    return result


def step_d_build_report(ta: dict) -> dict:
    """d) 生成简报文本，保存到 data/daily_report.json"""
    cs = ta.get("composite_score") or {
        "score": ta.get("score"),
        "verdict": ta.get("verdict"),
        "bull": None,
        "bear": None,
    }
    rsi = ta.get("rsi") if isinstance(ta.get("rsi"), dict) else {"value": ta.get("rsi"), "zone": "-"}
    ma = ta.get("ma") if isinstance(ta.get("ma"), dict) else {"arrangement": "-", "cross": "-"}
    boll = ta.get("boll") if isinstance(ta.get("boll"), dict) else {}
    kdj = ta.get("kdj") if isinstance(ta.get("kdj"), dict) else {}
    volume = ta.get("volume") if isinstance(ta.get("volume"), dict) else {"vol_vs_avg20": "-", "divergence": None}
    mtf = ta.get("multi_timeframe") if isinstance(ta.get("multi_timeframe"), dict) else {"resonance": "-"}
    gaps = ta.get("gaps") or []

    report = {
        "date": ta.get("current_date"),
        "price": ta.get("current_price"),
        "score": cs.get("score"),
        "verdict": cs.get("verdict"),
        "bull": cs.get("bull"),
        "bear": cs.get("bear"),
        "rsi": rsi.get("value"),
        "rsi_zone": rsi.get("zone"),
        "ma_arrangement": ma.get("arrangement"),
        "ma_cross": ma.get("cross"),
        "boll_position": boll.get("position"),
        "boll_squeeze": boll.get("squeeze"),
        "kdj_zone": kdj.get("zone"),
        "kdj_cross": kdj.get("cross"),
        "volume_vs_avg20": volume.get("vol_vs_avg20"),
        "volume_divergence": volume.get("divergence"),
        "mtf_resonance": mtf.get("resonance"),
        "gap_count": len(gaps),
    }
    price = report["price"]
    price_txt = f"{price:.2f}" if isinstance(price, (int, float)) else str(price)
    lines = [
        f"📊 上证指数技术简报 - {report['date']}",
        f"收盘价：{price_txt}",
        f"综合评分：{report['score']}（{report['verdict']}）",
        f"看多信号 {report['bull'] if report['bull'] is not None else '-'} / 看空信号 {report['bear'] if report['bear'] is not None else '-'}",
        "",
        f"RSI：{report['rsi']}（{report['rsi_zone']}）",
        f"均线：{report['ma_arrangement']} / {report['ma_cross']}",
        f"布林：{report['boll_position']} / {report['boll_squeeze']}",
        f"KDJ：{report['kdj_zone']} / {report['kdj_cross']}",
        f"量能：{report['volume_vs_avg20']} / {report['volume_divergence'] or '无背离'}",
        f"多周期：{report['mtf_resonance']}",
    ]
    if gaps:
        lines.append(f"缺口：最近 {len(gaps)} 个")
    report["brief"] = "\n".join(lines)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[简报] 已保存到 {REPORT_PATH}")
    return report


def step_e_push_if_strong(report: dict) -> None:
    """e) 如果评分绝对值 > 3（强烈信号），推送微信"""
    score = report["score"]
    if abs(score) <= 3:
        print(f"[推送] 评分={score}，绝对值≤3，跳过推送")
        return

    print(f"[推送] 评分={score}，绝对值>3，开始推送微信...")
    msg = report["brief"]
    try:
        result = subprocess.run(
            ["hermes", "send", "--to", "weixin", msg],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"[推送] 微信推送成功: {result.stdout.strip()}")
        else:
            print(f"[推送] 微信推送失败 (rc={result.returncode}): {result.stderr.strip()}",
                  file=sys.stderr)
    except FileNotFoundError:
        print("[推送] hermes CLI 未找到，尝试直接 POST ...")
        # fallback: 可通过 requests POST 到 hermes gateway
        try:
            import requests
            resp = requests.post(
                "http://localhost:9119/api/send",
                json={"target": "weixin", "message": msg},
                timeout=10,
            )
            print(f"[推送] HTTP 推送结果: {resp.status_code} {resp.text.strip()}")
        except Exception as e:
            print(f"[推送] HTTP 推送也失败: {e}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[推送] hermes send 超时", file=sys.stderr)


def main() -> int:
    print("=" * 50)
    print("每日收盘自动更新 - 开始")
    print("=" * 50)

    # a) 获取上证指数
    df_sh = step_a_fetch_index("上证指数", "sh000001", SH_PATH)

    # b) 获取创业板指数
    df_sz = step_b_fetch_sz()

    # c) 对上证指数做技术分析
    ta = step_c_technical_analysis(df_sh)

    # d) 生成简报
    report = step_d_build_report(ta)

    # e) 条件推送
    step_e_push_if_strong(report)

    print("=" * 50)
    print("每日收盘自动更新 - 完成")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
