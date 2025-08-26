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
TRADES_DB_ID = os.getenv("TRADES_DB_ID", "").strip()

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

# 交易表字段
TRADE_CODE_PROP = "Code"                # Rich text
TRADE_NAME_PROP = "基金名称"            # Title/Rich text
TRADE_TYPE_PROP = "交易类型"            # Select (买入/卖出)
TRADE_AMOUNT_PROP = "交易金额"          # Number
TRADE_QUANTITY_PROP = "交易份额"        # Number
TRADE_PRICE_PROP = "交易价格"           # Number
TRADE_DATE_PROP = "交易日期"            # Date
TRADE_RELATION_PROP = "Fund 持仓"       # Relation → 持仓表

# 计算结果字段（持仓表）
HOLDING_DAILY_PROFIT_PROP = "当日收益"  # Number
HOLDING_HOLDING_PROFIT_PROP = "持有收益" # Number
HOLDING_TOTAL_PROFIT_PROP = "总收益"    # Number
HOLDING_TOTAL_COST_PROP = "总持仓成本"  # Number
HOLDING_MARKET_VALUE_PROP = "市值"      # Number
HOLDING_PROFIT_RATE_PROP = "收益率"     # Number

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


def list_trades_pages() -> List[dict]:
    """获取所有交易页面"""
    pages = []
    cursor = None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        data = notion_request("POST", f"/databases/{TRADES_DB_ID}/query", payload)
        pages.extend(data.get("results") or [])
        cursor = data.get("next_cursor")
        if not data.get("has_more"):
            break
    return pages


def get_trades_by_code() -> Dict[str, List[dict]]:
    """按基金代码分组交易记录"""
    trades = list_trades_pages()
    trades_by_code = {}
    
    for trade in trades:
        props = trade.get("properties") or {}
        code = zpad6(get_prop_text(props.get(TRADE_CODE_PROP)))
        if not code:
            continue
            
        if code not in trades_by_code:
            trades_by_code[code] = []
        trades_by_code[code].append(trade)
    
    return trades_by_code


# ================ 收益计算 ================
def calculate_fund_profits(holding: dict, trades_by_code: Dict[str, List[dict]]) -> Dict[str, float]:
    """计算单个基金的收益数据"""
    props = holding.get("properties") or {}
    
    # 基本信息
    code = zpad6(get_prop_text(props.get(HOLDING_CODE_PROP)))
    name = get_prop_text(props.get(HOLDING_TITLE_PROP))
    
    # 当前市场数据
    current_price = safe_float(get_prop_number(props.get(HOLDING_GSZ_PROP)))
    if current_price <= 0:
        current_price = safe_float(get_prop_number(props.get(HOLDING_DWJZ_PROP)))
    
    daily_change_rate = safe_float(get_prop_number(props.get(HOLDING_GSZZL_PROP)))
    position = safe_float(get_prop_number(props.get(HOLDING_POSITION_PROP)))
    quantity = safe_float(get_prop_number(props.get(HOLDING_QUANTITY_PROP)))
    
    # 如果没有持仓数据，从交易记录计算
    if quantity <= 0 and code in trades_by_code:
        quantity = calculate_quantity_from_trades(trades_by_code[code])
    
    # 计算持仓成本
    total_cost = safe_float(get_prop_number(props.get(HOLDING_COST_PROP)))
    if total_cost <= 0 and code in trades_by_code:
        total_cost = calculate_cost_from_trades(trades_by_code[code])
    
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


def calculate_quantity_from_trades(trades: List[dict]) -> float:
    """从交易记录计算持有份额"""
    total_quantity = 0.0
    
    for trade in trades:
        props = trade.get("properties") or {}
        trade_type = get_prop_select(props.get(TRADE_TYPE_PROP))
        trade_quantity = safe_float(get_prop_number(props.get(TRADE_QUANTITY_PROP)))
        
        if trade_type == "买入":
            total_quantity += trade_quantity
        elif trade_type == "卖出":
            total_quantity -= trade_quantity
    
    return max(0, total_quantity)


def calculate_cost_from_trades(trades: List[dict]) -> float:
    """从交易记录计算总成本"""
    total_cost = 0.0
    
    for trade in trades:
        props = trade.get("properties") or {}
        trade_type = get_prop_select(props.get(TRADE_TYPE_PROP))
        trade_amount = safe_float(get_prop_number(props.get(TRADE_AMOUNT_PROP)))
        
        if trade_type == "买入":
            total_cost += trade_amount
        elif trade_type == "卖出":
            # 卖出时减少成本（简化处理）
            total_cost -= trade_amount
    
    return max(0, total_cost)


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


def update_all_holdings_profits() -> None:
    """更新所有持仓的收益数据"""
    print("开始计算基金收益数据...")
    
    holdings = list_holdings_pages()
    trades_by_code = get_trades_by_code()
    
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
            profits = calculate_fund_profits(holding, trades_by_code)
            
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


# ================ 主函数 ================
def main() -> None:
    """主函数"""
    if not NOTION_TOKEN:
        raise SystemExit("请设置 NOTION_TOKEN")
    if not HOLDINGS_DB_ID:
        raise SystemExit("请设置 HOLDINGS_DB_ID")
    if not TRADES_DB_ID:
        raise SystemExit("请设置 TRADES_DB_ID")
    
    mode = (sys.argv[1] if len(sys.argv) > 1 else "profit").lower()
    
    if mode == "profit":
        update_all_holdings_profits()
    else:
        print(f"未知模式: {mode}")
        print("支持的模式: profit")


if __name__ == "__main__":
    main()
