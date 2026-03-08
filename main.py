#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股监控系统 v1 - CEO 指令完成
2026-03-04 23:35 启动
"""

import json
import sqlite3
import time
import os
import pandas as pd
import requests
from datetime import datetime, timedelta
from pathlib import Path

# 配置
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "stocks.db"
WATCH_LIST_PATH = DATA_DIR / "watch_list.json"

# 初始化数据库
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            code TEXT PRIMARY KEY,
            name TEXT,
            current_price REAL,
            change_pct REAL,
            volume BIGINT,
            amount BIGINT,
            update_time TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            price REAL,
            change_pct REAL,
            volume BIGINT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 初始化关注列表
def init_watch_list():
    if not WATCH_LIST_PATH.exists():
        default_stocks = [
            {"code": "sh600519", "name": "贵州茅台", "buy_price": 1700.0},
            {"code": "sz000858", "name": "五粮液", "buy_price": 150.0},
            {"code": "sh601318", "name": "中国平安", "buy_price": 50.0},
        ]
        with open(WATCH_LIST_PATH, 'w') as f:
            json.dump(default_stocks, f, indent=2, ensure_ascii=False)
    return json.load(open(WATCH_LIST_PATH))

# 获取 A 股实时行情（用腾讯股市接口）
def fetch_realtime_data():
    """获取所有 A 股实时行情"""
    try:
        # 沪深 A 股列表
        url = "https://stock.gtimg.cn/data/index.php"
        params = {
            "app": "data",
            "action": "stock_search",
            "cCode": "shan",  # 深圳
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        
        # 直接列出一些重点股票的代码
        stocks = [
            ("sh600519", "贵州茅台"),
            ("sz000858", "五粮液"),
            ("sh601318", "中国平安"),
            ("sh601888", "中海达"),
            ("sz300750", "宁德时代"),
            ("sh600036", "招商银行"),
            ("sz000651", "格力电器"),
            ("sh600276", "恒瑞医药"),
            ("sz000333", "美的集团"),
            ("sh600887", "伊利股份"),
        ]
        
        # 腾讯行情接口支持批量查询
        codes_str = ",".join([s[0][2:] + "." + ("1" if s[0][:2] == "sh" else "0") for s in stocks])
        
        # 实时行情接口
        url = f"http://qt.gtimg.cn/s={codes_str}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = parse_stock_response(resp.text)
            return data
        else:
            return []
    except Exception as e:
        print(f"[ERROR] 获取实时行情失败: {e}")
        return []

def parse_stock_response(text):
    """解析腾讯行情接口返回"""
    stocks = []
    for line in text.strip().split('\n'):
        if not line.startswith('v_'):
            continue
        # 格式：v_s_sz000858="..."; 
        content = line.split('="')[1].rstrip('";')
        parts = content.split('~')
        if len(parts) < 33:
            continue
        try:
            stock = {
                "name": parts[0],
                "code": parts[1],
                "current_price": float(parts[3]),
                "yesterday_close": float(parts[4]),
                "open_price": float(parts[5]),
                "volume": float(parts[6]) * 100,  #手转股
                "amount": float(parts[7]) * 10000,  #万转元
                "bid_price": float(parts[8]),
                "ask_price": float(parts[9]),
                "high_price": float(parts[31]),
                "low_price": float(parts[32]),
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            stock["change_pct"] = (stock["current_price"] - stock["yesterday_close"]) / stock["yesterday_close"] * 100
            stocks.append(stock)
        except Exception as e:
            continue
    return stocks

# 数据库存储
def save_stock_data(stocks):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for s in stocks:
        cursor.execute('''
            INSERT OR REPLACE INTO stocks 
            (code, name, current_price, change_pct, volume, amount, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (s['code'], s['name'], s['current_price'], s['change_pct'], 
              int(s['volume']), int(s['amount']), now))
        
        cursor.execute('''
            INSERT INTO price_history (code, price, change_pct, volume, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (s['code'], s['current_price'], s['change_pct'], int(s['volume']), now))
    
    conn.commit()
    conn.close()

# 检测暴涨暴跌
def detect_significant_moves():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取最近5分钟的数据
    now = datetime.now()
    five_min_ago = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    
    # 找出涨跌幅超过5%的股票
    cursor.execute('''
        SELECT code, name, current_price, change_pct, update_time 
        FROM stocks 
        WHERE ABS(change_pct) > 5 
        AND update_time > ?
    ''', (five_min_ago,))
    
    results = cursor.fetchall()
    conn.close()
    
    return results

# 生成新闻关键词
def generate_news_keywords(stock_name, change_pct):
    """根据股票名称和涨跌幅生成新闻关键词"""
    if change_pct > 0:
        return f"{stock_name} 涨幅 新闻 公告"
    else:
        return f"{stock_name} 跌幅 新闻 公告 利空"

# 简易新闻/公告采集（模拟）
def fetch_recent_news(stock_name, keywords):
    """获取最近新闻（模拟）"""
    # 实际应接入东方财富网、同花顺等接口
    # 这里先返回模拟数据
    return [
        f"{stock_name} 最新公告：今日盘后公告无重大事项",
        f"行业动态：{stock_name} 所属行业今日整体表现平稳",
        f"市场评论：{stock_name} 波动属正常市场调整"
    ]

# 基本面评分卡
def get_fundamental_score(stock_code, current_price):
    """简单的基本面评分（0-100）"""
    # 模拟数据，实际应接入财报数据
    scores = {
        "sh600519": 85,  # 贵州茅台
        "sz000858": 78,  # 五粮液
        "sh601318": 72,  # 中国平安
        "sz300750": 68,  # 宁德时代
        "sh600036": 75,  # 招商银行
        "sz000651": 70,  # 格力电器
        "sh600276": 80,  # 恒瑞医药
        "sz000333": 76,  # 美的集团
        "sh600887": 73,  # 伊利股份
    }
    return scores.get(stock_code, 65)

# 判断利空/正常波动
def analyze_market_move(current_price, yesterday_close, news_list):
    """分析是利空还是正常波动"""
    change_pct = (current_price - yesterday_close) / yesterday_close * 100
    
    if abs(change_pct) < 3:
        return "正常波动", 0
    
    # 简易关键词匹配
    negative_keywords = ["利空", "处罚", "调查", "亏损", "退市", "监管"]
    positive_keywords = ["利好", "增长", "盈利", "合作", "订单", "反弹"]
    
    negative_count = sum(1 for news in news_list if any(kw in news for kw in negative_keywords))
    positive_count = sum(1 for news in news_list if any(kw in news for kw in positive_keywords))
    
    if negative_count > positive_count and change_pct < 0:
        return "疑似利空", -1
    elif positive_count > negative_count and change_pct > 0:
        return "疑似利好", 1
    else:
        return "市场情绪影响", 0

# 发送 Telegram 通知
def send_telegram_alert(message):
    """发送 Telegram 消息"""
    # 这里需要配置 Telegram Bot Token 和 Chat ID
    # 简易占位，实际应使用 Telegram API
    print(f"[ALERT] {message}")
    return True

# 生成每日报告
def generate_daily_report():
    """生成早盘/收盘报告"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取今日开盘价、最高、最低、收盘价
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    cursor.execute('''
        SELECT code, name, MIN(current_price), MAX(current_price), 
               AVG(current_price), COUNT(*) 
        FROM price_history 
        WHERE DATE(timestamp) = ?
        GROUP BY code, name
    ''', (today,))
    
    results = cursor.fetchall()
    conn.close()
    
    report = f"📊 A股监控日报 - {today}\n"
    report += "=" * 40 + "\n"
    
    for row in results:
        code, name, min_p, max_p, avg_p, count = row
        report += f"{name} ({code})\n"
        report += f"  今最低: {min_p:.2f} | 今最高: {max_p:.2f} | 今均价: {avg_p:.2f}\n"
        report += f"  观察次数: {count}\n\n"
    
    return report

# 主程序
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 股票监控系统启动")
    
    # 初始化
    init_db()
    watch_list = init_watch_list()
    
    # 实时监控循环
    while True:
        stocks = fetch_realtime_data()
        if stocks:
            save_stock_data(stocks)
            
            # 检测异常波动
            moves = detect_significant_moves()
            if moves:
                for move in moves:
                    code, name, price, pct, _ = move
                    print(f"[异常波动] {name} ({code}) 涨跌幅: {pct:.2f}% 价格: {price:.2f}")
                    
                    # 获取新闻
                    keywords = generate_news_keywords(name, pct)
                    news = fetch_recent_news(name, keywords)
                    
                    # 分析
                    yesterday_close = price / (1 + pct / 100) if pct != 0 else price
                    analysis, sentiment = analyze_market_move(price, yesterday_close, news)
                    
                    # 基本面评分
                    score = get_fundamental_score(code, price)
                    
                    # 生成警报
                    alert_msg = f"⚡ {name} ({code}) 异动警报\n"
                    alert_msg += f"价格: {price:.2f}  涨跌幅: {pct:.2f}%\n"
                    alert_msg += f"分析: {analysis} | 基本面评分: {score}/100\n"
                    alert_msg += f"新闻摘要: {news[0] if news else '暂无最新消息'}"
                    
                    print(alert_msg)
                    # send_telegram_alert(alert_msg)  # 实际发送
        
        # 每30秒刷新一次
        time.sleep(30)

if __name__ == "__main__":
    main()
