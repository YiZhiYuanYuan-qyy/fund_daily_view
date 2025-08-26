#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Notion Fund Daily View

计算基金日常数据：
1) 当日收益（基于持仓和当日涨跌幅）
2) 持有收益（基于持仓成本和当前估值）
3) 总收益（当日收益 + 持有收益）
4) 持仓成本（总投入成本）
"""

import os
import sys
import time
import json
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP

import requests


# ================== 环境变量 ==================
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
HOLDINGS_DB_ID = os.getenv("HOLDINGS_DB_ID", "").strip()
DAILY_DATA_DB_ID = os.getenv("DAILY_DATA_DB_ID", "").strip()

# ============== 字段名配置 ==============
# 持仓表字段
HOLDING_TITLE_PROP = "基金名称"          # Title
HOLDING_CODE_PROP = "Code"              # Rich text
HOLDING_DWJZ_PROP = "单位净值"          # Number
HOLDING_GSZ_PROP = "估算净值"           # Number
HOLDING_GSZZL_PROP = "估算涨跌幅"       # Number
HOLDING_COST_PROP = "持仓成本"          # Number/Formula/Rollup
HOLDING_POSITION_PROP = "仓位"          # Number
HOLDING_QUANTITY_PROP = "持有份额"      # Number



# 计算结果字段（持仓表）
HOLDING_DAILY_PROFIT_PROP = "当日收益"  # Number
HOLDING_HOLDING_PROFIT_PROP = "持有收益" # Number
HOLDING_TOTAL_PROFIT_PROP = "总收益"    # Number
HOLDING_TOTAL_COST_PROP = "总持仓成本"  # Number
HOLDING_MARKET_VALUE_PROP = "市值"      # Number
HOLDING_PROFIT_RATE_PROP = "收益率"     # Number

# 每日数据表字段
DAILY_DATA_TITLE_PROP = "日期"          # Title
DAILY_DATA_DAILY_PROFIT_PROP = "当日收益"   # Number
DAILY_DATA_TOTAL_COST_PROP = "持仓成本"     # Number
DAILY_DATA_TOTAL_PROFIT_PROP = "总收益"     # Number

# ================== Notion API ==================
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# ================ 工具函数 ================
SG_TZ = timezone(timedelta(hours=8))  # Asia/Singapore


def today_iso_date() -> str:
    return datetime.now(SG_TZ).date().isoformat()


def zpad6(s: str) -> str:
    """将基金代码补零到6位"""
    t = "".join(ch for ch in str(s or "").strip() if ch.isdigit())
    return t.zfill(6) if t else ""


def notion_request(method: str, path: str, payload=None) -> dict:
    """发送 Notion API 请求"""
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(payload) if payload is not None else None
    resp = requests.request(
        method, url, headers=NOTION_HEADERS, data=data, timeout=25
    )
    if not resp.ok:
        raise RuntimeError(
            f"Notion {method} {path} failed: "
            f"{resp.status_code} {resp.text}"
        )
    return resp.json()


def get_prop_text(prop: dict) -> str:
    """从 Notion 属性中提取文本值"""
    if not prop:
        return ""
    t = prop.get("type")
    if t == "rich_text":
        arr = prop.get("rich_text") or []
        return "".join((x.get("plain_text") or "") for x in arr).strip()
    if t == "title":
        arr = prop.get("title") or []
        return "".join((x.get("plain_text") or "") for x in arr).strip()
    if t == "number":
        v = prop.get("number")
        return "" if v is None else str(v)
    return ""


def get_prop_number(prop: dict) -> Optional[float]:
    """从 Notion 属性中提取数值"""
    if not prop:
        return None
    t = prop.get("type")
    if t == "number":
        return prop.get("number")
    if t == "formula":
        f = prop.get("formula") or {}
        if f.get("type") == "number":
            return f.get("number")
    if t == "rollup":
        r = prop.get("rollup") or {}
        if r.get("type") == "number":
            return r.get("number")
    return None


def get_prop_date(prop: dict) -> Optional[str]:
    """从 Notion 属性中提取日期"""
    if not prop:
        return None
    if prop.get("type") == "date":
        date_obj = prop.get("date")
        if date_obj and date_obj.get("start"):
            return date_obj.get("start")
    return None


def get_prop_select(prop: dict) -> Optional[str]:
    """从 Notion 属性中提取选择值"""
    if not prop:
        return None
    if prop.get("type") == "select":
        select_obj = prop.get("select")
        if select_obj:
            return select_obj.get("name")
    return None


def safe_float(value, default=0.0) -> float:
    """安全转换为浮点数"""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def round_decimal(value: float, places: int = 2) -> float:
    """四舍五入到指定小数位"""
    return float(Decimal(str(value)).quantize(
        Decimal('0.' + '0' * places), rounding=ROUND_HALF_UP
    ))


# ================ 数据获取 ================
def list_holdings_pages() -> List[dict]:
    """获取所有持仓页面"""
    pages = []
    cursor = None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        data = notion_request("POST", f"/databases/{HOLDINGS_DB_ID}/query", payload)
        pages.extend(data.get("results") or [])
        cursor = data.get("next_cursor")
        if not data.get("has_more"):
            break
    return pages





# ================ 收益计算 ================
def calculate_fund_profits(holding: dict) -> Dict[str, float]:
    """计算单个基金的收益数据"""
    props = holding.get("properties") or {}
    
    # 调试：打印所有可用的字段名
    print(f"[DEBUG] 可用字段: {list(props.keys())}")
    
    # 基本信息
    code = zpad6(get_prop_text(props.get(HOLDING_CODE_PROP)))
    name = get_prop_text(props.get(HOLDING_TITLE_PROP))
    
    print(f"[DEBUG] {code} {name}")
    
    # 当前市场数据
    current_price = safe_float(get_prop_number(props.get(HOLDING_GSZ_PROP)))
    if current_price <= 0:
        current_price = safe_float(get_prop_number(props.get(HOLDING_DWJZ_PROP)))
    
    daily_change_rate = safe_float(get_prop_number(props.get(HOLDING_GSZZL_PROP)))
    position = safe_float(get_prop_number(props.get(HOLDING_POSITION_PROP)))
    quantity = safe_float(get_prop_number(props.get(HOLDING_QUANTITY_PROP)))
    
    print(f"[DEBUG] current_price={current_price}, daily_change_rate={daily_change_rate}, quantity={quantity}")
    
    # 持有份额应该通过 Rollup 自动计算，如果为0可能是数据问题
    if quantity <= 0:
        print(f"警告: {code} {name} 的持有份额为0，可能需要检查 Rollup 配置")
    
    # 直接使用持仓表中的持仓成本
    total_cost = safe_float(get_prop_number(props.get(HOLDING_COST_PROP)))
    
    print(f"[DEBUG] total_cost={total_cost}")
    
    # 计算收益
    market_value = current_price * quantity
    daily_profit = market_value * (daily_change_rate / 100)
    holding_profit = market_value - total_cost
    total_profit = daily_profit + holding_profit
    profit_rate = (holding_profit / total_cost * 100) if total_cost > 0 else 0
    
    return {
        "code": code,
        "name": name,
        "current_price": round_decimal(current_price, 4),
        "daily_change_rate": round_decimal(daily_change_rate, 2),
        "quantity": round_decimal(quantity, 2),
        "total_cost": round_decimal(total_cost, 2),
        "market_value": round_decimal(market_value, 2),
        "daily_profit": round_decimal(daily_profit, 2),
        "holding_profit": round_decimal(holding_profit, 2),
        "total_profit": round_decimal(total_profit, 2),
        "profit_rate": round_decimal(profit_rate, 2)
    }








# ================ 数据更新 ================
def update_holding_profits(holding_id: str, profits: Dict[str, float]) -> None:
    """更新持仓表的收益数据"""
    props = {
        HOLDING_DAILY_PROFIT_PROP: {"number": profits["daily_profit"]},
        HOLDING_HOLDING_PROFIT_PROP: {"number": profits["holding_profit"]},
        HOLDING_TOTAL_PROFIT_PROP: {"number": profits["total_profit"]},
        HOLDING_TOTAL_COST_PROP: {"number": profits["total_cost"]},
        HOLDING_MARKET_VALUE_PROP: {"number": profits["market_value"]},
        HOLDING_PROFIT_RATE_PROP: {"number": profits["profit_rate"]},
    }
    
    notion_request(
        "PATCH",
        f"/pages/{holding_id}",
        {"properties": props}
    )


def get_previous_day_total_profit(current_date_str: str) -> float:
    """获取前一天的总收益"""
    if not DAILY_DATA_DB_ID:
        return 0.0
    
    # 计算前一天的日期
    from datetime import datetime, timedelta
    current_date = datetime.fromisoformat(current_date_str.replace('@', ''))
    previous_date = current_date - timedelta(days=1)
    previous_date_str = f"@{previous_date.strftime('%Y-%m-%d')}"
    
    # 查询前一天的记录
    payload = {
        "filter": {
            "property": DAILY_DATA_TITLE_PROP,
            "title": {"equals": previous_date_str}
        },
        "page_size": 1
    }
    
    try:
        data = notion_request("POST", f"/databases/{DAILY_DATA_DB_ID}/query", payload)
        results = data.get("results") or []
        
        if results:
            props = results[0].get("properties") or {}
            previous_total_profit = get_prop_number(props.get(DAILY_DATA_TOTAL_PROFIT_PROP))
            return safe_float(previous_total_profit)
        else:
            print(f"[INFO] 未找到前一天({previous_date_str})的记录，总收益从0开始计算")
            return 0.0
            
    except Exception as exc:
        print(f"[WARN] 获取前一天总收益失败: {exc}")
        return 0.0


def create_or_update_daily_data(date_str: str, daily_profit: float, total_cost: float, previous_total_profit: float) -> None:
    """创建或更新每日数据表记录"""
    if not DAILY_DATA_DB_ID:
        print("[WARN] 未设置 DAILY_DATA_DB_ID，跳过每日数据记录")
        return
    
    print(f"[DEBUG] create_or_update_daily_data 参数:")
    print(f"  date_str: {date_str}")
    print(f"  daily_profit: {daily_profit}")
    print(f"  total_cost: {total_cost}")
    print(f"  previous_total_profit: {previous_total_profit}")
    
    # 计算累计总收益 = 前一天总收益 + 当日收益
    cumulative_total_profit = previous_total_profit + daily_profit
    
    # 检查今日记录是否已存在
    payload = {
        "filter": {
            "property": DAILY_DATA_TITLE_PROP,
            "title": {"equals": date_str}
        },
        "page_size": 1
    }
    
    data = notion_request("POST", f"/databases/{DAILY_DATA_DB_ID}/query", payload)
    existing = data.get("results") or []
    
    props = {
        DAILY_DATA_TITLE_PROP: {"title": [{"text": {"content": date_str}}]},
        DAILY_DATA_DAILY_PROFIT_PROP: {"number": daily_profit},
        DAILY_DATA_TOTAL_COST_PROP: {"number": total_cost},
        DAILY_DATA_TOTAL_PROFIT_PROP: {"number": cumulative_total_profit}
    }
    
    if existing:
        # 更新现有记录
        page_id = existing[0]["id"]
        notion_request("PATCH", f"/pages/{page_id}", {"properties": props})
        print(f"[DAILY] 更新每日数据: {date_str}")
    else:
        # 创建新记录
        notion_request(
            "POST",
            "/pages",
            {
                "parent": {"database_id": DAILY_DATA_DB_ID},
                "properties": props
            }
        )
        print(f"[DAILY] 创建每日数据: {date_str}")
    
    print(f"[DAILY] 累计总收益计算: 前一天({previous_total_profit:+.2f}) + 当日({daily_profit:+.2f}) = {cumulative_total_profit:+.2f}")


def update_all_holdings_profits() -> None:
    """更新所有持仓的收益数据"""
    print("开始计算基金收益数据...")
    
    holdings = list_holdings_pages()
    
    total = len(holdings)
    updated = 0
    failed = 0
    
    # 计算汇总数据
    summary = {
        "total_cost": 0.0,
        "total_market_value": 0.0,
        "total_daily_profit": 0.0,
        "total_holding_profit": 0.0,
        "total_profit": 0.0
    }
    
    for holding in holdings:
        try:
            profits = calculate_fund_profits(holding)
            
            # 更新持仓数据
            update_holding_profits(holding["id"], profits)
            
            # 累计汇总数据
            summary["total_cost"] += profits["total_cost"]
            summary["total_market_value"] += profits["market_value"]
            summary["total_daily_profit"] += profits["daily_profit"]
            summary["total_holding_profit"] += profits["holding_profit"]
            summary["total_profit"] += profits["total_profit"]
            
            print(
                f"[PROFIT] {profits['code']} {profits['name']} | "
                f"当日: {profits['daily_profit']:+.2f} | "
                f"持有: {profits['holding_profit']:+.2f} | "
                f"总收益: {profits['total_profit']:+.2f} | "
                f"收益率: {profits['profit_rate']:+.2f}%"
            )
            
            updated += 1
            
        except Exception as exc:
            print(f"[ERR] 计算收益失败 {holding.get('id', 'unknown')}: {exc}")
            failed += 1
    
    # 打印汇总信息
    print("\n" + "="*60)
    print("📊 基金收益汇总")
    print("="*60)
    print(f"总持仓成本: ¥{summary['total_cost']:,.2f}")
    print(f"总市值: ¥{summary['total_market_value']:,.2f}")
    print(f"当日收益: ¥{summary['total_daily_profit']:+,.2f}")
    print(f"持有收益: ¥{summary['total_holding_profit']:+,.2f}")
    print(f"总收益: ¥{summary['total_profit']:+,.2f}")
    
    if summary['total_cost'] > 0:
        total_profit_rate = (summary['total_profit'] / summary['total_cost']) * 100
        print(f"总收益率: {total_profit_rate:+.2f}%")
    
    print("="*60)
    print(f"PROFIT Done. updated={updated}, failed={failed}, total={total}")
    
    # 记录每日数据
    today = today_iso_date()
    today_str = f"@{today}"
    try:
        # 获取前一天的总收益
        previous_total_profit = get_previous_day_total_profit(today_str)
        
        print(f"[DEBUG] 准备写入每日数据:")
        print(f"  日期: {today_str}")
        print(f"  当日收益: {summary['total_daily_profit']}")
        print(f"  持仓成本: {summary['total_cost']}")
        print(f"  前一天总收益: {previous_total_profit}")
        
        create_or_update_daily_data(
            date_str=today_str,
            daily_profit=round_decimal(summary['total_daily_profit'], 2),
            total_cost=round_decimal(summary['total_cost'], 2),
            previous_total_profit=previous_total_profit
        )
    except Exception as exc:
        print(f"[ERR] 记录每日数据失败: {exc}")


# ================ 主函数 ================
def main() -> None:
    """主函数"""
    if not NOTION_TOKEN:
        raise SystemExit("请设置 NOTION_TOKEN")
    if not HOLDINGS_DB_ID:
        raise SystemExit("请设置 HOLDINGS_DB_ID")
    if not DAILY_DATA_DB_ID:
        print("[WARN] 未设置 DAILY_DATA_DB_ID，将跳过每日数据记录")
    
    mode = (sys.argv[1] if len(sys.argv) > 1 else "profit").lower()
    
    if mode == "profit":
        update_all_holdings_profits()
    else:
        print(f"未知模式: {mode}")
        print("支持的模式: profit")


if __name__ == "__main__":
    main()
