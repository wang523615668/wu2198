#!/usr/bin/env python3
"""
wu2198 投资助手引擎 v1
以wu2198观点为核心，所有分析结果围绕他的框架展开

核心原则：
1. 指数定方向（波浪+技术步伐）
2. 板块定方向（他的持仓方向）
3. 个股定标的（池内优先）
4. 节奏定操作（关键点位触发）
5. 风控定仓位（他的仓位逻辑）
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── wu2198核心观点库（持续更新） ──

WU_VIEWPOINTS = {
    "last_updated": "2026-06-27",
    
    # 波浪框架
    "wave_framework": {
        "wave_1": {"start": 2689, "end": 3674, "status": "完成", "pct": "+36.6%"},
        "wave_2": {"start": 3674, "end": 3040, "status": "完成", "type": "ABC调整", "pct": "-17.3%"},
        "wave_3": {"start": 3040, "end": 4258, "status": "完成", "sub_waves": "5小浪I-V", "pct": "+40.1%"},
        "wave_4": {"start": 4258, "end": None, "status": "进行中", "note": "当前处于第四大浪调整"},
        "wave_5": {"start": None, "end": None, "status": "待定", "probability": "60%", "target": "4600-4800"},
    },
    
    # 上证技术步伐
    "sh_key_levels": {
        "turn_down_from": 4175,
        "resistance": 4132,
        "break_4070_target": 4031,
        "gap_support": 3987,
        "current_note": "自4258调整压力趋势线(4258-4175连线)，破4070→4031→3987缺口，下周看3987-4070取向",
    },
    
    # 创业板技术转点
    "cyb_key_levels": {
        "short_term_pivot": 4150,
        "medium_term_pivot": 3750,
        "m_head_risk": "跌破4150需考虑小M头可能",
        "current_note": "不破则维持原来波段趋势",
    },
    
    # 当前策略基调（2026-06-27更新，基于微博实时抓取）
    "current_stance": {
        "risk_level": "较高",
        "direction": "第四浪调整期，等待下探3987缺口后判断",
        "key_phrase": "近八成个股没有上涨，只是结构牛+科技牛",
        # ⚠️ 重要转向：6月24日起wu2198已转向看多医药
        "stock_direction": "创新药/医药/生物已提前起来（6/24原话）",
        "stock_direction_detail": "科技股5月初就该收手，亏钱的人不少。资金正从科技切换到医药。白酒6/26说'不排除有阶段性机会'",
        "position_advice": "轻仓布局医药创新药方向，科技股减仓，白酒可关注长周期机会",
        "trigger_to_buy": "指数下探3987缺口企稳+第五浪启动信号",
        # wu2198对各板块态度
        "sector_views": {
            "创新药/医药/生物": "✅ 已提前起来，龙头改写新高，重点方向",
            "科技/半导体": "⚠️ 5月初就该收手，现在亏钱的人不少。但6/26盘中仍点评半导体硅片/LED",
            "白酒": "🟡 本周异动但行业趋势继续压制。长周期不排除有阶段性机会（6/26原话）",
            "银行": "👀 防守板块，观察走势判断小登强弱",
            "医疗服务": "✅ 有冲板和20厘米，跟随创新药方向",
            "LED/Micro LED": "👀 6/26出现冲20厘米，整体表现可以",
            "商业航天": "👀 6/26出现冲板的",
            "黄金": "❌ 伦敦金从5598调整近30%，看向3500美元",
        },
    },
    
    # 仓位逻辑（基于wu2198历史风格推断）
    "position_logic": {
        "强烈看多": {"仓位": "8成+", "动作": "积极做多核心股"},
        "偏多": {"仓位": "5-7成", "动作": "持有为主，逢低加核心"},
        "中性": {"仓位": "3-5成", "动作": "观望为主，小仓试水"},
        "偏空": {"仓位": "1-3成", "动作": "减仓，只留核心"},
        "强烈看空": {"仓位": "0-1成", "动作": "空仓或极轻仓"},
    },
    
    # 重要判断锚点
    "anchors": [
        "第一大浪2689-3674已完成",
        "第二大浪ABC调整至3040已完成",
        "3040点的'干'字是第三浪起点",
        "第三浪5小浪到4258(实际试了4258)已完成",
        "当前是第四大浪调整",
        "第五大浪(第三轮行情)能否出现目前无法判断",
        "创业板短线看4150得失，中线看3750",
        "⚠️ 6/24 wu2198转向：创新药/医药/生物已提前起来",
        "⚠️ 科技股5月初就该收手，亏钱的人不少",
        "❌ 白酒继续受压，汾酒/贡酒/老窖等试探新低",
        "🏦 银行医疗是防守板块，观察银行走势",
    ],
}


def get_wu_stance() -> dict:
    """获取wu2198当前立场"""
    return WU_VIEWPOINTS["current_stance"]


def reconcile_with_wu(
    tech_score: float,
    tech_verdict: str,
    current_price: float,
    index: str = "sh",
) -> dict:
    """
    将技术指标评分与wu2198观点对齐
    核心：wu2198观点优先，技术指标辅助
    """
    wu = get_wu_stance()
    wave = WU_VIEWPOINTS["wave_framework"]
    
    # ── 1. 确定wu2198方向 ──
    wu_direction = "adjustment"  # 第四浪调整
    wu_bias = "偏空"  # 调整期偏空
    wu_sub_text = "第四浪调整中，但第五浪概率60%"
    
    # 上证关键点位
    if index == "sh":
        levels = WU_VIEWPOINTS["sh_key_levels"]
        if current_price > levels["resistance"]:
            wu_direction = "recovery"
            wu_bias = "偏多"
            wu_sub_text = "突破反压位，可能结束调整"
        elif current_price < 3674:
            wu_direction = "deep_correction"
            wu_bias = "强烈看空"
            wu_sub_text = "跌破第一浪顶3674，波浪结构需重估"
    else:
        levels = WU_VIEWPOINTS["cyb_key_levels"]
        short_p = levels["short_term_pivot"]
        med_p = levels["medium_term_pivot"]
        if current_price > short_p:
            wu_bias = "中性偏多"
            wu_sub_text = "短线转点之上，维持波段趋势"
        elif current_price > med_p:
            wu_bias = "偏空"
            wu_sub_text = "破短线转点，注意M头风险"
        else:
            wu_bias = "强烈看空"
            wu_sub_text = "破中线转点3750，趋势可能反转"
    
    # ── 2. 融合评分 ──
    # wu2198观点权重60%，技术指标权重40%
    wu_score_map = {
        "强烈看多": 3.0,
        "偏多": 1.5,
        "中性偏多": 0.5,
        "中性": 0,
        "偏空": -1.5,
        "中性偏空": -0.8,
        "强烈看空": -3.0,
    }
    wu_score = wu_score_map.get(wu_bias, 0)
    
    # 融合：wu2198 60% + 技术 40%
    blended = wu_score * 0.6 + tech_score * 0.4
    
    # ── 3. 方向修正 ──
    if blended >= 2:
        final_verdict = "强烈看多🐂🐂🐂"
        action = "积极做多核心股，8成仓位"
    elif blended >= 1:
        final_verdict = "偏多🐂"
        action = "持有为主逢低加仓，5-7成仓位"
    elif blended >= 0:
        final_verdict = "中性观望😐"
        action = "轻仓观望，等待wu2198调整结束信号"
    elif blended >= -1.5:
        final_verdict = "偏空🐻"
        action = "减仓只留核心，1-3成仓位"
    else:
        final_verdict = "强烈看空🐻🐻🐻"
        action = "空仓或极轻仓，等待第四浪调整结束"
    
    # ── 4. 关键提醒 ──
    alerts = []
    
    # 上证关键点位提醒
    if index == "sh":
        if current_price < levels["break_4070_target"]:
            alerts.append(f"⚠️ 已破{levels['break_4070_target']}技术目标位，下一步看3792-3674支撑区")
        if current_price > levels["resistance"]:
            alerts.append(f"🌟 突破反压{levels['resistance']}，调整可能结束")
    
    # 创业板提醒
    if index == "cyb":
        if current_price < short_p * 1.02:
            alerts.append(f"⚠️ 接近短线转点{short_p}，跌破看M头")
        if current_price < med_p * 1.03:
            alerts.append(f"🔴 接近中线转点{med_p}，破则趋势反转")
    
    # 波浪提醒
    alerts.append(f"📍 当前处于第四大浪调整，第五浪概率{wave['wave_5']['probability']}")
    alerts.append(f"💡 wu2198策略：{wu['key_phrase']}，{wu['stock_direction']}")
    
    # ── 5. 操作节奏 ──
    rhythm = {
        "current_phase": "第四浪调整期",
        "what_to_do": "轻仓布局创新药/医药方向，科技股减仓",
        "watch_for": "医药龙头持续走强+白酒止跌+指数站稳反压位",
        "avoid": "追高科技股、抄底白酒、重仓",
        "best_stocks": "创新药龙头（恒瑞/百济）+ 医疗器械 + CXO",
    }
    
    return {
        "wu_direction": wu_direction,
        "wu_bias": wu_bias,
        "wu_score": wu_score,
        "tech_score": tech_score,
        "blended_score": round(blended, 1),
        "verdict": final_verdict,
        "action": action,
        "sub_text": wu_sub_text,
        "alerts": alerts,
        "rhythm": rhythm,
        "wu_viewpoint": wu,
    }


def evaluate_stock_with_wu(
    stock_name: str,
    stock_code: str,
    in_pool: bool,
    sector: str = "",
    tech_score: float = 0,
    tech_verdict: str = "",
    pool_info: dict = None,
) -> dict:
    """
    以wu2198视角评价个股
    核心：池内优先 + 方向匹配 + 技术辅助
    """
    wu = get_wu_stance()
    direction = wu["stock_direction"]  # "挖掘滞涨科技股"
    
    # ── 1. 池内加分 ──
    pool_bonus = 0
    pool_label = ""
    if in_pool:
        bucket = pool_info.get("bucket", "") if pool_info else ""
        score = pool_info.get("score", 0) if pool_info else 0
        if "核心" in bucket:
            pool_bonus = 2.0
            pool_label = "🌟 核心股"
        elif "弹性" in bucket:
            pool_bonus = 1.0
            pool_label = "⚡ 弹性股"
        else:
            pool_bonus = 0.5
            pool_label = "👁️ 关注股"
    else:
        pool_label = "❌ 非池内"
    
    # ── 2. 方向匹配度 ──
    direction_match = 0
    direction_label = ""
    code_prefix = stock_code[:3] if len(stock_code) >= 3 else ""
    
    # wu2198当前重点方向：创新药/医药/生物（6/24转向）
    pharma_kw = ["医药", "创新药", "生物", "医疗", "CXO", "器械", "制药", "中药", "药", "恒瑞", "百济", "药明", "迈瑞", "智飞", "爱尔"]
    tech_kw = ["半导体", "芯片", "通信", "电子", "软件", "IT", "科技", "信息", "华创", "中芯", "中微", "拓荆", "华海"]
    baijiu_kw = ["白酒", "酒", "茅台", "五粮液", "汾酒", "老窖", "泸州", "贵州茅", "五粮", "洋河", "古井"]
    all_text = f"{sector} {stock_name}"
    is_pharma = any(kw in all_text for kw in pharma_kw)
    is_tech = any(kw in all_text for kw in tech_kw)
    code_prefix = stock_code[:3] if len(stock_code) >= 3 else ""
    if not is_tech and code_prefix == "688":
        is_tech = True
    
    # 医药方向（当前重点）
    if is_pharma:
        direction_match = 2.0
        direction_label = "🎯 完美匹配'创新药/医药/生物'方向（wu2198最新重点）"
    # 科技方向（wu2198已提示风险）
    elif is_tech:
        direction_match = -1.0
        direction_label = "⚠️ 科技方向-wu2198说5月初就该收手"
    # 白酒（明确看空）
    elif any(kw in all_text for kw in baijiu_kw):
        direction_match = -2.0
        direction_label = "❌ 白酒方向-wu2198说继续受压试探新低"
    # 银行（防守观察）
    elif "银行" in all_text:
        direction_match = 0.5
        direction_label = "👀 银行方向-防守板块，观察走势"
    else:
        direction_match = 0
        direction_label = "↔️ 非当前重点方向"
    
    # ── 3. 综合评分 ──
    # 权重：池内30% + 方向匹配30% + 技术40%
    final = pool_bonus * 0.3 + direction_match * 0.3 + tech_score * 0.4
    
    # ── 4. 操作建议 ──
    if final >= 2:
        suggestion = "🟢 可逢低布局，符合wu2198方向"
        position = "可配1-2成"
    elif final >= 0.5:
        suggestion = "🟡 观察为主，等调整结束再考虑"
        position = "试探仓位0.5成"
    elif final >= -1:
        suggestion = "🟠 暂不参与，不符合当前方向"
        position = "0仓"
    else:
        suggestion = "🔴 回避，与技术面和方向均冲突"
        position = "0仓"
    
    # ── 5. wu2198视角一句话 ──
    if is_pharma and in_pool:
        one_liner = f"✅ {stock_name}是wu2198当前重点方向(医药)+池内股，可关注低吸"
    elif is_pharma:
        one_liner = f"💊 {stock_name}符合wu2198最新医药方向，6/24确认创新药龙头已改写新高"
    elif is_tech and in_pool:
        one_liner = f"⚠️ {stock_name}虽在池内但科技方向-wu2198说5月初就该收手，减仓为宜"
    elif is_tech:
        one_liner = f"🔴 {stock_name}科技方向-wu2198明确提示风险，亏钱的人不少"
    elif any(kw in sector for kw in ["白酒", "酒"]):
        one_liner = f"❌ {stock_name}白酒方向-wu2198说继续受压，汾酒/老窖试探新低"
    elif in_pool:
        one_liner = f"👁️ {stock_name}在池内但非当前重点方向，等方向切换"
    else:
        one_liner = f"❌ {stock_name}不在wu2198当前关注范围"
    
    return {
        "stock_name": stock_name,
        "stock_code": stock_code,
        "pool_status": pool_label,
        "direction_match": direction_label,
        "wu_final_score": round(final, 1),
        "suggestion": suggestion,
        "position": position,
        "one_liner": one_liner,
    }


def daily_strategy(
    sh_price: float,
    cyb_price: float,
    tech_score_sh: float,
    tech_verdict_sh: str,
) -> dict:
    """
    生成每日策略报告
    以wu2198观点为纲，一句话策略
    """
    # 大盘判断
    sh_view = reconcile_with_wu(tech_score_sh, tech_verdict_sh, sh_price, "sh")
    cyb_view = reconcile_with_wu(tech_score_sh, tech_verdict_sh, cyb_price, "cyb")
    
    # 每日一句话
    wu = get_wu_stance()
    today = datetime.now().strftime("%Y-%m-%d")
    
    if sh_price < 3674:
        headline = "🔴 破位！跌破第一浪顶3674，第四浪可能升级为更大调整"
    elif sh_price < 4031:
        headline = "🟡 调整深化，接近关键技术支撑区，耐心等待"
    elif sh_price < 4132:
        headline = "🟡 第四浪调整中，反压4132之下偏弱"
    elif sh_price < 4258:
        headline = "🟢 站上反压位，关注第五浪启动信号"
    else:
        headline = "🐂 突破前高，第五浪可能已启动"
    
    # 操作节奏
    if sh_view["blended_score"] >= 0:
        rhythm_text = "调整期可轻仓布局创新药/医药方向，wu2196月24日确认创新药龙头已改写新高"
    else:
        rhythm_text = "调整未结束，科技股减仓（wu2198说5月初就该收手），关注医药方向低吸机会"
    
    strategy = {
        "date": today,
        "headline": headline,
        "sh_view": sh_view,
        "cyb_view": cyb_view,
        "strategy_summary": {
            "大盘方向": sh_view["verdict"],
            "仓位建议": sh_view["action"],
            "操作节奏": rhythm_text,
            "重点方向": wu["stock_direction"],
            "方向详情": wu.get("stock_direction_detail", ""),
            "关注个股": "创新药龙头(恒瑞/百济)+医疗器械+CXO",
            "回避方向": "科技股(5月初该收手)+白酒(继续受压)",
            "风险提示": wu["key_phrase"],
        },
        "wu2198_anchors": WU_VIEWPOINTS["anchors"],
        "key_levels": {
            "上证": {k: v for k, v in WU_VIEWPOINTS["sh_key_levels"].items()},
            "创业板": {k: v for k, v in WU_VIEWPOINTS["cyb_key_levels"].items()},
        },
    }
    
    return strategy


if __name__ == "__main__":
    # 测试：上证4027点
    print("=== 上证指数(4027) wu2198视角 ===")
    r = reconcile_with_wu(-4.8, "强烈看空", 4027, "sh")
    print(f"  wu2198方向: {r['wu_bias']}")
    print(f"  融合评分: {r['blended_score']} → {r['verdict']}")
    print(f"  操作: {r['action']}")
    print(f"  提醒:")
    for a in r["alerts"]:
        print(f"    {a}")
    
    print("\n=== 创业板(4194) wu2198视角 ===")
    r2 = reconcile_with_wu(-2.0, "偏空", 4194, "cyb")
    print(f"  wu2198方向: {r2['wu_bias']}")
    print(f"  融合评分: {r2['blended_score']} → {r2['verdict']}")
    
    print("\n=== 个股评价：中芯国际 ===")
    r3 = evaluate_stock_with_wu("中芯国际", "688981", True, "半导体", -0.5, "偏空", {"bucket": "核心个股", "score": 100})
    print(f"  池内: {r3['pool_status']}")
    print(f"  方向: {r3['direction_match']}")
    print(f"  评分: {r3['wu_final_score']} → {r3['suggestion']}")
    print(f"  仓位: {r3['position']}")
    print(f"  一句话: {r3['one_liner']}")
    
    print("\n=== 每日策略 ===")
    ds = daily_strategy(4027, 4194, -4.8, "强烈看空")
    print(f"  {ds['headline']}")
    for k, v in ds["strategy_summary"].items():
        print(f"  {k}: {v}")
