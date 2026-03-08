#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票期货全量监控系统 v2 - CEO 指令完成
2026-03-04 23:47 升级
"""

import json
import sqlite3
import time
import os
import re
import pandas as pd
import requests
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

# 配置
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "stocks.db"
WATCH_LIST_PATH = DATA_DIR / "watch_list.json"
FUTURES_LIST_PATH = DATA_DIR / "futures_list.json"

# 全量股票代码（A股 + 科创板 + 创业板）
def fetch_all_a_stock_codes():
    """获取所有 A 股代码"""
    stocks = []
    try:
        # 沪市主板
        url = "http://43.push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "5000",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0 t:6,m:0 t:80",
            "fields": "f12,f14",
            "_": int(time.time() * 1000)
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data", {}).get("diff", []):
                code = item.get("f12", "")
                if code:
                    if code.startswith("6"):
                        code = "sh" + code
                    elif code.startswith("0"):
                        code = "sz" + code
                    elif code.startswith("3"):
                        code = "sz" + code
                    stocks.append({"code": code, "name": item.get("f14", "")})
        
        # 沪市科创板
        params["fs"] = "m:0 t:7"
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data", {}).get("diff", []):
                code = item.get("f12", "")
                if code.startswith("688"):
                    stocks.append({"code": "sh" + code, "name": item.get("f14", "")})
        
        # 深市创业板
        url = "http://43.push2.eastmoney.com/api/qt/clist/get"
        params["fs"] = "m:0 t:80"
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data", {}).get("diff", []):
                code = item.get("f12", "")
                if code.startswith("300"):
                    stocks.append({"code": "sz" + code, "name": item.get("f14", "")})
    except Exception as e:
        print(f"[ERROR] 获取A股代码失败: {e}")
    
    # 补充常用股票
    补充股票 = [
        {"code": "sh600519", "name": "贵州茅台"},
        {"code": "sz000858", "name": "五粮液"},
        {"code": "sh601318", "name": "中国平安"},
        {"code": "sh600036", "name": "招商银行"},
        {"code": "sz000651", "name": "格力电器"},
    ]
    
    for 补 in 补充股票:
        if not any(s["code"] == 补["code"] for s in stocks):
            stocks.append(补)
    
    return stocks

# 东方财富期货代码列表
def fetch_futures_list():
    """获取东方财富期货列表"""
    futures = []
    try:
        # 期货主力合约
        url = "http://futsales.eastmoney.com/ER_FuturesMainClickPad/GetFutureMainList"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("Data", []):
                code = item.get("Symbol", "")
                if code:
                    futures.append({
                        "code": code,
                        "name": item.get("ShortName", ""),
                        "market": "期货"
                    })
    except Exception as e:
        print(f"[ERROR] 获取期货代码失败: {e}")
    
    # 常用期货补充
    常用期货 = [
        {"code": "HNSEMI", "name": "文华油脂指数", "market": "期货"},
        {"code": "HNNI", "name": "文华工业品指数", "market": "期货"},
        {"code": "HNAg", "name": "银主连", "market": "期货"},
        {"code": "HNCu", "name": "铜主连", "market": "期货"},
        {"code": "HNAu", "name": "金主连", "market": "期货"},
        {"code": "HNIa", "name": "铁矿主连", "market": "期货"},
        {"code": "HNSc", "name": "原油主连", "market": "期货"},
        {"code": "HNOa", "name": "OA油菜籽", "market": "期货"},
        {"code": "HNBa", "name": "白砂糖", "market": "期货"},
        {"code": "HNBu", "name": "铜期货", "market": "期货"},
        {"code": "HNBa", "name": "白糖期货", "market": "期货"},
        {"code": "HNec", "name": "鸡蛋期货", "market": "期货"},
        {"code": "HNic", "name": "鸡蛋期货", "market": "期货"},
        {"code": "HNal", "name": "铝主连", "market": "期货"},
        {"code": "HNzn", "name": "锌主连", "market": "期货"},
        {"code": "HNpb", "name": "铅主连", "market": "期货"},
        {"code": "HNni", "name": "镍主连", "market": "期货"},
        {"code": "HNsn", "name": "锡主连", "market": "期货"},
        {"code": "HNsi", "name": "硅主连", "market": "期货"},
        {"code": "HNaO", "name": "甲醇主连", "market": "期货"},
        {"code": "HNMA", "name": "甲醇主连", "market": "期货"},
        {"code": "HNapp", "name": "苹果期货", "market": "期货"},
        {"code": "HNCa", "name": "碳酸钙", "market": "期货"},
        {"code": "HNjm", "name": "粳米期货", "market": "期货"},
        {"code": "HNlr", "name": "陇原梨", "market": "期货"},
        {"code": "HNft", "name": "废纸期货", "market": "期货"},
        {"code": "HN_csi", "name": "中证期货指数", "market": "期货"},
    ]
    
    for 期 in 常用期货:
        if not any(f["code"] == 期["code"] for f in futures):
            futures.append(期)
    
    return futures

# 获取实时行情
def fetch_realtime_data_all():
    """获取所有股票和期货实时行情"""
    stocks = fetch_all_a_stock_codes()
    futures = fetch_futures_list()
    
    all_items = stocks + futures
    
    results = []
    
    # 分批请求（避免过快）
    for i in range(0, len(all_items), 100):
        batch = all_items[i:i+100]
        try:
            codes_str = ",".join([s["code"] for s in batch])
            url = f"http://quote.eastmoney.com/center/api/search?permissions=1&keywords={codes_str}&page=1&pagesize=100"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    try:
                        code = item.get("code", "")
                        name = item.get("name", "")
                        price = float(item.get("price", 0))
                        change_pct = float(item.get("percent", 0))
                        volume = float(item.get("volume", 0))
                        amount = float(item.get("amount", 0))
                        
                        results.append({
                            "code": code,
                            "name": name,
                            "current_price": price,
                            "change_pct": change_pct,
                            "volume": int(volume),
                            "amount": int(amount),
                            "market": "股票" if code[:2] in ["sh", "sz"] else "期货",
                            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                    except Exception:
                        continue
        except Exception as e:
            print(f"[ERROR] 批次获取失败: {e}")
    
    return results

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
            market TEXT,
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
            market TEXT,
            timestamp TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            name TEXT,
            price REAL,
            change_pct REAL,
            score INTEGER,
            reason TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 保存数据
def save_stock_data(stocks):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for s in stocks:
        cursor.execute('''
            INSERT OR REPLACE INTO stocks 
            (code, name, current_price, change_pct, volume, amount, market, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (s['code'], s['name'], s['current_price'], s['change_pct'], 
              int(s.get('volume', 0)), int(s.get('amount', 0)), s.get('market', '股票'), now))
        
        cursor.execute('''
            INSERT INTO price_history (code, price, change_pct, volume, market, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (s['code'], s['current_price'], s['change_pct'], int(s.get('volume', 0)), s.get('market', '股票'), now))
    
    conn.commit()
    conn.close()

# 检测异常波动和机会
def detect_opportunities():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now()
    five_min_ago = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    
    # 找出涨跌幅超过 3% 或 成交量暴增的股票
    cursor.execute('''
        SELECT code, name, current_price, change_pct, volume, update_time, market 
        FROM stocks 
        WHERE ABS(change_pct) > 3 
        OR (volume > 1000000 AND change_pct > 0)
        AND update_time > ?
    ''', (five_min_ago,))
    
    results = cursor.fetchall()
    conn.close()
    
    opportunities = []
    for row in results:
        code, name, price, pct, volume, time, market = row
        score = 50
        
        # 涨幅加分
        if pct > 0:
            score += min(int(pct * 5), 30)
        else:
            score -= min(int(abs(pct) * 5), 30)
        
        # 成交量加分
        if volume > 1000000:
            score += 10
        
        # 市场类型修正
        if market == "期货":
            score += 5
        
        # 开仓机会
        if pct > 5:
            reason = "涨幅%5，放量突破"
        elif pct > 3 and volume > 500000:
            reason = "涨幅%3，放量活跃"
        elif pct < -5:
            reason = "跌幅%5，超卖机会"
        else:
            reason = "异常波动"
        
        if score > 60 or (score > 40 and pct < -3):
            opportunities.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": pct,
                "score": min(max(score, 0), 100),
                "reason": reason,
                "market": market
            })
    
    return opportunities

# 生成可视化面板数据
def generate_dashboard_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 最新数据
    cursor.execute('''
        SELECT code, name, current_price, change_pct, volume, market 
        FROM stocks 
        ORDER BY ABS(change_pct) DESC 
        LIMIT 50
    ''')
    recent_data = cursor.fetchall()
    
    # 异常波动
    cursor.execute('''
        SELECT code, name, current_price, change_pct, volume, update_time, market 
        FROM stocks 
        WHERE ABS(change_pct) > 5 
        ORDER BY ABS(change_pct) DESC
    ''')
    volatility_data = cursor.fetchall()
    
    # 机会列表
    opportunities = detect_opportunities()
    
    conn.close()
    
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recent": [
            {
                "code": r[0],
                "name": r[1],
                "price": r[2],
                "pct": r[3],
                "volume": r[4],
                "market": r[5]
            }
            for r in recent_data
        ],
        "volatility": [
            {
                "code": r[0],
                "name": r[1],
                "price": r[2],
                "pct": r[3],
                "volume": r[4],
                "time": r[5],
                "market": r[6]
            }
            for r in volatility_data
        ],
        "opportunities": opportunities,
        "summary": {
            "total_stocks": len(recent_data),
            "volatility_count": len(volatility_data),
            "opportunity_count": len(opportunities)
        }
    }

# 生成 HTML 面板
def generate_html_dashboard():
    data = generate_dashboard_data()
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>A股+期货监控面板 - CEO Task #002</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; }}
        h1 {{ color: #89b4fa; margin-bottom: 20px; }}
        .summary {{ background: #313244; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .summary-item {{ display: inline-block; margin: 0 20px; font-size: 18px; }}
        .summary-item span {{ color: #89b4fa; font-weight: bold; }}
        .panel {{ background: #313244; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .panel h2 {{ color: #f38ba8; border-bottom: 1px solid #45475a; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #45475a; }}
        th {{ background: #45475a; color: #f5e0dc; }}
        .trending-up {{ color: #a6e3a1; }}
        .trending-down {{ color: #f38ba8; }}
        .opportunity {{ background: #313244 !important; }}
        .score-80 {{ border-left: 4px solid #a6e3a1; }}
        .score-50 {{ border-left: 4px solid #f9e2af; }}
        .score-low {{ border-left: 4px solid #f38ba8; }}
        .market-stock {{ color: #89b4fa; }}
        .market-future {{ color: #fab387; }}
    </style>
</head>
<body>
    <h1>📊 A股+期货实时监控面板</h1>
    
    <div class="summary">
        <div class="summary-item"> TimothyStamp: <span>{data['timestamp']}</span></div>
        <div class="summary-item">观察股票: <span>{data['summary']['total_stocks']}</span></div>
        <div class="summary-item">异常波动: <span class="trending-down">{data['summary']['volatility_count']}</span></div>
        <div class="summary-item">机会提示: <span class="trending-up">{data['summary']['opportunity_count']}</span></div>
    </div>
    
    <div class="panel">
        <h2>🔥 涨跌幅 TOP10</h2>
        <table>
            <tr><th>代码</th><th>名称</th><th>价格</th><th>涨跌幅</th><th>成交量</th><th>市场</th></tr>
"""
    
    for item in data['recent'][:10]:
        pct_class = "trending-up" if item['pct'] >= 0 else "trending-down"
        market_class = "market-stock" if item['market'] == "股票" else "market-future"
        html += f"""
            <tr>
                <td>{item['code']}</td>
                <td>{item['name']}</td>
                <td>{item['price']:.2f}</td>
                <td class="{pct_class}">{item['pct']:.2f}%</td>
                <td>{item['volume']:,}</td>
                <td class="{market_class}">{item['market']}</td>
            </tr>"""
    
    html += """</table></div>
    
    <div class="panel">
        <h2>⚠️ 异常波动列表（≥5%）</h2>
        <table>
            <tr><th>代码</th><th>名称</th><th>价格</th><th>涨跌幅</th><th>成交量</th><th>市场</th></tr>
"""
    
    for item in data['volatility']:
        pct_class = "trending-up" if item['pct'] >= 0 else "trending-down"
        market_class = "market-stock" if item['market'] == "股票" else "market-future"
        html += f"""
            <tr>
                <td>{item['code']}</td>
                <td>{item['name']}</td>
                <td>{item['price']:.2f}</td>
                <td class="{pct_class}">{item['pct']:.2f}%</td>
                <td>{item['volume']:,}</td>
                <td class="{market_class}">{item['market']}</td>
            </tr>"""
    
    html += """</table></div>
    
    <div class="panel">
        <h2>💡 机会提示（智能评分 ≥50）</h2>
        <table>
            <tr><th>代码</th><th>名称</th><th>价格</th><th>涨跌幅</th><th>评分</th><th>理由</th><th>市场</th></tr>
"""
    
    for opp in data['opportunities'][:20]:
        score = opp['score']
        if score >= 80:
            score_class = "score-80"
        elif score >= 50:
            score_class = "score-50"
        else:
            score_class = "score-low"
        
        market_class = "market-stock" if opp['market'] == "股票" else "market-future"
        html += f"""
            <tr class="{score_class}">
                <td>{opp['code']}</td>
                <td>{opp['name']}</td>
                <td>{opp['price']:.2f}</td>
                <td class="{'trending-up' if opp['change_pct'] >= 0 else 'trending-down'}">{opp['change_pct']:.2f}%</td>
                <td><span class="{pct_class}">{score}</span>/100</td>
                <td>{opp['reason']}</td>
                <td class="{market_class}">{opp['market']}</td>
            </tr>"""
    
    html += """</table></div>
    
    <script>
        setInterval(function() {{
            document.querySelector('.summary .summary-item span:last-child').textContent = '""" + data['timestamp'] + """';
        }}, 1000);
    </script>
</body>
</html>"""
    
    return html

# 主程序
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 股票期货全量监控系统启动")
    
    # 初始化
    init_db()
    
    # 实时监控循环
    while True:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始采集...")
        stocks = fetch_realtime_data_all()
        
        if stocks:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取到 {len(stocks)} 条数据")
            save_stock_data(stocks)
            
            # 检测机会
            opportunities = detect_opportunities()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发现 {len(opportunities)} 个机会")
            
            # 生成面板
            html = generate_html_dashboard()
            panel_path = DATA_DIR / "dashboard.html"
            with open(panel_path, 'w') as f:
                f.write(html)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 面板已更新: {panel_path}")
        
        # 每30秒刷新一次
        time.sleep(30)

if __name__ == "__main__":
    main()
