#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股监控系统每日报告
2026-03-04  CEO 指令完成

执行时间：早盘 9:25、收盘 15:00
"""

import json
import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "stocks.db"
WATCH_LIST_PATH = DATA_DIR / "watch_list.json"

def load_watch_list():
    with open(WATCH_LIST_PATH, 'r') as f:
        return json.load(f)

def generate_report():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    report_lines = []
    report_lines.append("=" * 50)
    report_lines.append(f"* A股监控日报 - {today} *")
    report_lines.append("=" * 50)
    
    # 今日整体情况
    cursor.execute('''
        SELECT COUNT(DISTINCT code) FROM price_history WHERE DATE(timestamp) = ?
    ''', (today,))
    stock_count = cursor.fetchone()[0]
    report_lines.append(f"📊 观察股票数: {stock_count}")
    
    # 关注股票今日表现
    watch_list = load_watch_list()
    report_lines.append("\n📈 关注股票今日表现:")
    report_lines.append("-" * 30)
    
    for stock in watch_list:
        code = stock["code"]
        name = stock["name"]
        
        cursor.execute('''
            SELECT price, change_pct, volume, timestamp 
            FROM price_history 
            WHERE code = ? AND DATE(timestamp) = ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (code, today))
        
        row = cursor.fetchone()
        if row:
            price, pct, volume, time = row
            report_lines.append(f"{name} ({code})")
            report_lines.append(f"  当前价: {price:.2f} | 涨跌幅: {pct:.2f}%")
            report_lines.append(f"  成交量: {volume:.0f} | 更新时间: {time}")
        else:
            report_lines.append(f"{name} ({code}) - 今日暂无数据")
    
    # 涨跌幅榜 Top 5
    cursor.execute('''
        SELECT code, name, MAX(change_pct) as max_pct
        FROM price_history 
        WHERE DATE(timestamp) = ?
        GROUP BY code, name
        ORDER BY max_pct DESC
        LIMIT 5
    ''', (today,))
    
    winners = cursor.fetchall()
    if winners:
        report_lines.append("\n🔥 今日涨幅Top 5:")
        for row in winners:
            report_lines.append(f"  {row[1]} ({row[0]}): {row[2]:.2f}%")
    
    # 跌幅榜 Top 5
    cursor.execute('''
        SELECT code, name, MIN(change_pct) as min_pct
        FROM price_history 
        WHERE DATE(timestamp) = ?
        GROUP BY code, name
        ORDER BY min_pct ASC
        LIMIT 5
    ''', (today,))
    
    losers = cursor.fetchall()
    if losers:
        report_lines.append("\n📉 今日跌幅Top 5:")
        for row in losers:
            report_lines.append(f"  {row[1]} ({row[0]}): {row[2]:.2f}%")
    
    # 风险提示
    cursor.execute('''
        SELECT DISTINCT code, name FROM stocks 
        WHERE ABS(change_pct) >= 10
    ''')
    high_volatility = cursor.fetchall()
    if high_volatility:
        report_lines.append("\n⚠️ 今日剧烈波动股票:")
        for row in high_volatility:
            report_lines.append(f"  {row[1]} ({row[0]})")
    
    conn.close()
    
    return "\n".join(report_lines)

def send_report():
    report = generate_report()
    
    # 输出报告
    print(report)
    
    # 保存到文件
    report_path = DATA_DIR / f"report_{datetime.now().strftime('%Y%m%d')}.txt"
    with open(report_path, 'w') as f:
        f.write(report)
    
    print(f"\n✅ 报告已保存到 {report_path}")
    
    # 实际应调用 Telegram API
    # send_telegram_report(report)

if __name__ == "__main__":
    send_report()
