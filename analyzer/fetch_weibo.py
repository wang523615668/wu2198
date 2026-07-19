#!/usr/bin/env python3
"""
wu2198微博抓取脚本 - 基于astron-weibo-mcp游客态
无需Cookie，自动获取游客session
"""
import sys
sys.path.insert(0, '/root/.hermes/hermes-agent/venv/lib/python3.11/site-packages')

from weibo_mcp.server import create_session, CONTAINER_API_URL, TAG_RE
import json, re
from datetime import datetime

WU2198_UID = "1216826604"
CONTAINER_ID = f"107603{WU2198_UID}"

INVEST_KEYWORDS = [
    "股", "涨", "跌", "浪", "点", "仓", "买", "卖", "行情",
    "医药", "科技", "白酒", "创新药", "半导体", "指数", "板块",
    "茅台", "老登", "小登", "医疗", "生物", "银行", "调",
    "盈利", "目标", "收手", "科技牛", "结构", "缺", "压力",
    "LED", "硅片", "航天", "创业板", "缺口", "反压", "反弹",
    "抵抗", "趋势", "资金", "流出", "流入", "成交",
]


def fetch_wu2198(pages: int = 5, invest_only: bool = True) -> list:
    """抓取wu2198最新微博"""
    session = create_session(prime_home=True)
    all_posts = []
    
    for page in range(1, pages + 1):
        params = {"containerid": CONTAINER_ID, "page": page}
        try:
            resp = session.get(CONTAINER_API_URL, params=params, timeout=20)
            data = resp.json()
        except Exception as e:
            print(f"⚠️ 第{page}页抓取失败: {e}")
            break
        
        cards = data.get("data", {}).get("cards", [])
        for c in cards:
            mb = c.get("mblog", {})
            if not mb:
                continue
            text = TAG_RE.sub("", mb.get("text", "")).strip()
            created = mb.get("created_at", "")
            mid = mb.get("mid", "")
            
            if not text or len(text) < 5:
                continue
            
            if invest_only and not any(kw in text for kw in INVEST_KEYWORDS):
                continue
            
            all_posts.append({
                "mid": mid,
                "created_at": created,
                "text": text[:500],
            })
    
    return all_posts


def extract_viewpoints(posts: list) -> dict:
    """从微博中提取关键投资观点"""
    viewpoints = {
        "fetch_time": datetime.now().isoformat(),
        "total_posts": len(posts),
        "sector_views": {},
        "index_views": {},
        "key_messages": [],
    }
    
    for p in posts:
        text = p["text"]
        date = p["created_at"]
        
        # 板块观点提取
        if any(kw in text for kw in ["创新药", "医药", "医疗", "生物"]):
            viewpoints["sector_views"]["医药"] = viewpoints["sector_views"].get("医药", [])
            viewpoints["sector_views"]["医药"].append({"date": date, "text": text[:200]})
        
        if any(kw in text for kw in ["白酒", "茅台", "酒"]):
            viewpoints["sector_views"]["白酒"] = viewpoints["sector_views"].get("白酒", [])
            viewpoints["sector_views"]["白酒"].append({"date": date, "text": text[:200]})
        
        if any(kw in text for kw in ["半导体", "科技", "芯片", "硅片"]):
            viewpoints["sector_views"]["科技/半导体"] = viewpoints["sector_views"].get("科技/半导体", [])
            viewpoints["sector_views"]["科技/半导体"].append({"date": date, "text": text[:200]})
        
        if any(kw in text for kw in ["银行", "金融"]):
            viewpoints["sector_views"]["银行"] = viewpoints["sector_views"].get("银行", [])
            viewpoints["sector_views"]["银行"].append({"date": date, "text": text[:200]})
        
        # 指数观点
        if any(kw in text for kw in ["指数", "创业板", "缺口", "反压", "调整压力"]):
            viewpoints["index_views"][date] = text[:200]
        
        # 关键信息
        if any(kw in text for kw in ["收手", "目标", "盈利", "结构牛", "行情"]):
            viewpoints["key_messages"].append({"date": date, "text": text[:300]})
    
    return viewpoints


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--all", action="store_true", help="包括非投资类")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    posts = fetch_wu2198(pages=args.pages, invest_only=not args.all)
    
    if args.json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
    else:
        print(f"=== wu2198最新微博 ({len(posts)}条) ===\n")
        for p in posts:
            print(f"📅 {p['created_at']}")
            print(f"   {p['text'][:300]}")
            print()
        
        print("\n=== 观点提取 ===")
        vp = extract_viewpoints(posts)
        for sector, msgs in vp["sector_views"].items():
            print(f"\n📦 {sector}:")
            for m in msgs[-3:]:
                print(f"  {m['date']}: {m['text'][:150]}")
        
        if vp["key_messages"]:
            print(f"\n🔑 关键信息:")
            for m in vp["key_messages"][-5:]:
                print(f"  {m['date']}: {m['text'][:200]}")
