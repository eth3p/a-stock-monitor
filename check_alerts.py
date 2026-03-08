#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票监控系统提醒规则引擎
2026-03-08 v6.1 异常检测算法优化完成
""" 

import json
import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "stocks.db"
WATCH_LIST_PATH = DATA_DIR / "watch_list.json"

# 时间窗口配置（分钟）
ALERT_WINDOWS = [5, 15, 30]

# 成交量阈值配置（手数）
VOLUME_THRESHOLD_MIN = 10000  # 最小成交量过滤阈值

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

# 加载历史价格数据
def load_price_history(minutes=30):
    """加载指定时间范围内的历史数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now()
    start_time = (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        SELECT code, price, change_pct, volume, timestamp 
        FROM price_history 
        WHERE timestamp >= ?
        ORDER BY code, timestamp
    ''', (start_time,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return rows

# 计算多时间窗口涨跌幅
def calculate_window_changes(code, history_data):
    """计算指定股票在不同时间窗口的涨跌幅"""
    window_changes = {}
    
    # 按时间排序
    sorted_data = sorted(history_data, key=lambda x: x[4])
    
    # 获取当前价格
    current_price = None
    for row in sorted_data:
        if row[0] == code:
            current_price = row[1]
            break
    
    if current_price is None:
        return window_changes
    
    # 按时间窗口计算
    for minutes in ALERT_WINDOWS:
        now = datetime.now()
        start_time = (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        
        window_prices = [
            row[1] for row in sorted_data 
            if row[0] == code and row[4] >= start_time
        ]
        
        if len(window_prices) >= 2:
            start_price = window_prices[0]
            change_pct = (current_price - start_price) / start_price * 100
            window_changes[f"{minutes}分钟"] = {
                "start_price": start_price,
                "current_price": current_price,
                "change_pct": change_pct,
                "data_points": len(window_prices)
            }
    
    return window_changes

# 检查成交量过滤
def check_volume_filter(code, current_volume, window_minutes=5):
    """检查成交量是否达到过滤阈值"""
    # 计算5分钟平均成交量
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now()
    start_time = (now - timedelta(minutes=window_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        SELECT AVG(volume) 
        FROM price_history 
        WHERE code = ? AND timestamp >= ?
    ''', (code, start_time))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        avg_volume = result[0]
        # 成交量大于平均值的2倍才触发
        return current_volume > avg_volume * 2
    return current_volume > VOLUME_THRESHOLD_MIN

# 优化涨跌幅计算逻辑
def calculate_optimized_change_pct(code, current_price):
    """基于历史数据优化涨跌幅计算"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取今日开盘价
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    cursor.execute('''
        SELECT MIN(timestamp), MAX(timestamp) 
        FROM price_history 
        WHERE DATE(timestamp) = ?
    ''', (today,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        # 获取开盘价
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT price 
            FROM price_history 
            WHERE code = ? AND timestamp >= ?
            ORDER BY timestamp LIMIT 1
        ''', (code, result[0]))
        
        open_result = cursor.fetchone()
        conn.close()
        
        if open_result:
            open_price = open_result[0]
            return (current_price - open_price) / open_price * 100
    
    # 如果无法获取开盘价，返回当前数据库中的涨跌幅
    prices = load_latest_prices()
    if code in prices:
        return prices[code]["change_pct"]
    
    return 0.0

# 生成提醒（增强版）
def generate_alerts():
    watch_list = load_watch_list()
    prices = load_latest_prices()
    
    alerts = []
    
    # 加载历史数据
    history_data = load_price_history(max(ALERT_WINDOWS) + 5)
    
    for stock in watch_list:
        code = stock["code"]
        name = stock["name"]
        target_price = stock.get("buy_price", 0)
        
        if code not in prices:
            continue
        
        current_price = prices[code]["price"]
        current_volume = prices[code]["volume"]
        
        # 优化涨跌幅计算（基于今日开盘价）
        optimized_pct = calculate_optimized_change_pct(code, current_price)
        
        # 多时间窗口检测
        window_changes = calculate_window_changes(code, history_data)
        
        # 成交量过滤检查
        volume_exceeds = check_volume_filter(code, current_volume)
        
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
        
        # 多时间窗口涨跌幅检测
        for window_name, data in window_changes.items():
            pct = data["change_pct"]
            
            # 涨幅超过5%
            if pct >= 5.0:
                alerts.append({
                    "type": f"RISE_{window_name}_5PCT",
                    "code": code,
                    "name": name,
                    "current_price": current_price,
                    "change_pct": pct,
                    "window": window_name,
                    "message": f"📈 {name} {window_name}涨幅 {pct:.2f}% (≥5%)"
                })
            
            # 跌幅超过5%
            if pct <= -5.0:
                alerts.append({
                    "type": f"DROP_{window_name}_5PCT",
                    "code": code,
                    "name": name,
                    "current_price": current_price,
                    "change_pct": pct,
                    "window": window_name,
                    "message": f"📉 {name} {window_name}跌幅 {pct:.2f}% (≥5%)"
                })
        
        # 单日跌幅检测（基于优化计算）
        if optimized_pct <= -5.0:
            alerts.append({
                "type": "DROP_5PCT",
                "code": code,
                "name": name,
                "current_price": current_price,
                "change_pct": optimized_pct,
                "message": f"📉 {name} 单日跌幅 {optimized_pct:.2f}% (≥5%)"
            })
        
        # 单日跌幅超过10%
        if optimized_pct <= -10.0:
            alerts.append({
                "type": "DROP_10PCT",
                "code": code,
                "name": name,
                "current_price": current_price,
                "change_pct": optimized_pct,
                "message": f"💣 {name} 单日跌幅 {optimized_pct:.2f}% (≥10%) - 严重警告"
            })
        
        # 成交量异常检测（仅在满足成交量过滤时）
        if volume_exceeds and abs(optimized_pct) >= 3.0:
            alerts.append({
                "type": "VOLUME_SPIKE",
                "code": code,
                "name": name,
                "current_price": current_price,
                "change_pct": optimized_pct,
                "volume": current_volume,
                "message": f"📊 {name} 成交量激增 {current_volume:,.0f}手，涨跌幅 {optimized_pct:.2f}%"
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
