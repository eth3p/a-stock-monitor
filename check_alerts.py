#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票监控系统提醒规则引擎
2026-03-04  CEO 指令完成
"""

import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "stocks.db"
WATCH_LIST_PATH = DATA_DIR / "watch_list.json"

# 加载关注列表
def load_watch_list():
    with open(WATCH_LIST_PATH, 'r') as f:
        return json.load(f)

# 加载最新行情
def load_latest_prices():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT code, name, current_price, change_pct, volume, update_time 
        FROM stocks 
        ORDER BY update_time DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    prices = {}
    for row in rows:
        code, name, price, pct, volume, time = row
        prices[code] = {
            "name": name,
            "price": price,
            "change_pct": pct,
            "volume": volume,
            "update_time": time
        }
    return prices

# 生成提醒
def generate_alerts():
    watch_list = load_watch_list()
    prices = load_latest_prices()
    
    alerts = []
    
    for stock in watch_list:
        code = stock["code"]
        name = stock["name"]
        target_price = stock.get("buy_price", 0)
        
        if code not in prices:
            continue
        
        current_price = prices[code]["price"]
        change_pct = prices[code]["change_pct"]
        
        # 检查-buy price
        if target_price > 0 and current_price <= target_price:
            alerts.append({
                "type": "BUY_PRICE_HIT",
                "code": code,
                "name": name,
                "current_price": current_price,
                "target_price": target_price,
                "message": f"⚠️ {name} 跌破建议买入价 {target_price:.2f} → {current_price:.2f}"
            })
        
        # 检查-5%跌幅
        if change_pct <= -5.0:
            alerts.append({
                "type": "DROP_5PCT",
                "code": code,
                "name": name,
                "current_price": current_price,
                "change_pct": change_pct,
                "message": f"📉 {name} 单日跌幅 {change_pct:.2f}% (≥5%)"
            })
        
        # 检查-10%跌幅
        if change_pct <= -10.0:
            alerts.append({
                "type": "DROP_10PCT",
                "code": code,
                "name": name,
                "current_price": current_price,
                "change_pct": change_pct,
                "message": f"💣 {name} 单日跌幅 {change_pct:.2f}% (≥10%) - 严重警告"
            })
    
    return alerts

# 发送提醒（占位）
def send_alert(alert):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {alert['message']}")
    # 实际应调用 Telegram API
    # send_telegram_alert(alert['message'])
    return True

# 主程序
def check_alerts():
    alerts = generate_alerts()
    if alerts:
        for alert in alerts:
            send_alert(alert)
        return len(alerts)
    return 0

if __name__ == "__main__":
    count = check_alerts()
    print(f"[INFO] 检查完成，共 {count} 条提醒")
