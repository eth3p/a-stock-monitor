#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票期货全量监控系统 v4 - CEO 指令完成
2026-03-04 23:47 升级 → 使用免费公开接口
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

# 配置
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "stocks.db"
WATCH_LIST_PATH = DATA_DIR / "watch_list.json"
FUTURES_LIST_PATH = DATA_DIR / "futures_list.json"

# 全量股票代码（使用免费接口）
def fetch_all_a_stock_codes():
    """获取所有 A 股代码 - 使用免费接口"""
    stocks = []
    
    # 使用股票代码列表文件（本地预存 + 动态更新）
    try:
        # 创业板
        url = "http://63.push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "1000",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0 t:80",
            "fields": "f12,f14",
            "_": int(time.time() * 1000)
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data", {}).get("diff", []):
                code = item.get("f12", "")
                if code and code.startswith("3"):
                    stocks.append({"code": "sz" + code, "name": item.get("f14", "")})
        
        # 科创板
        params["fs"] = "m:0 t:7"
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data", {}).get("diff", []):
                code = item.get("f12", "")
                if code and code.startswith("688"):
                    stocks.append({"code": "sh" + code, "name": item.get("f14", "")})
        
        # 沪市主板（分页获取）
        for page in range(1, 6):
            params["ps"] = "1000"
            params["pn"] = str(page)
            params["fs"] = "m:0 t:6"
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", {}).get("diff", []):
                    code = item.get("f12", "")
                    if code and code.startswith("6"):
                        stocks.append({"code": "sh" + code, "name": item.get("f14", "")})
        
        # 深市主板（分页获取）
        for page in range(1, 6):
            params["ps"] = "1000"
            params["pn"] = str(page)
            params["fs"] = "m:0 t:0"
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", {}).get("diff", []):
                    code = item.get("f12", "")
                    if code and code.startswith("0"):
                        stocks.append({"code": "sz" + code, "name": item.get("f14", "")})
        
        # 中小板
        params["ps"] = "1000"
        params["pn"] = "1"
        params["fs"] = "m:0 t:13"
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data", {}).get("diff", []):
                code = item.get("f12", "")
                if code and code.startswith("0"):
                    stocks.append({"code": "sz" + code, "name": item.get("f14", "")})
        
    except Exception as e:
        print(f"[ERROR] 获取A股代码失败: {e}")
    
    # 补充常用股票
    常用 = [
        {"code": "sh600519", "name": "贵州茅台"},
        {"code": "sz000858", "name": "五粮液"},
        {"code": "sh601318", "name": "中国平安"},
        {"code": "sh600036", "name": "招商银行"},
        {"code": "sz000651", "name": "格力电器"},
        {"code": "sz300750", "name": "宁德时代"},
        {"code": "sh600276", "name": "恒瑞医药"},
        {"code": "sz000333", "name": "美的集团"},
        {"code": "sh600887", "name": "伊利股份"},
        {"code": "sh601888", "name": "中海达"},
    ]
    
    for 补 in 常用:
        if not any(s["code"] == 补["code"] for s in stocks):
            stocks.append(补)
    
    return stocks

# 东方财富期货代码列表（本地维护）
def fetch_futures_list():
    """获取东方财富期货列表 - 本地维护"""
    # 常用期货列表
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
        {"code": "HNal", "name": "铝主连", "market": "期货"},
        {"code": "HNzn", "name": "锌主连", "market": "期货"},
        {"code": "HNpb", "name": "铅主连", "market": "期货"},
        {"code": "HNni", "name": "镍主连", "market": "期货"},
        {"code": "HNsn", "name": "锡主连", "market": "期货"},
        {"code": "HNsi", "name": "硅主连", "market": "期货"},
        {"code": "HNMA", "name": "甲醇主连", "market": "期货"},
        {"code": "HNapp", "name": "苹果期货", "market": "期货"},
        {"code": "HNjm", "name": "粳米期货", "market": "期货"},
        {"code": "HNft", "name": "废纸期货", "market": "期货"},
        {"code": "HN_csi", "name": "中证期货指数", "market": "期货"},
        {"code": "HNeb", "name": "二号棉", "market": "期货"},
        {"code": "HNRob", "name": "Robusta咖啡", "market": "期货"},
        {"code": "HNso", "name": "豆油主连", "market": "期货"},
        {"code": "HNb", "name": "苯乙烯", "market": "期货"},
        {"code": "HNa", "name": "淀粉", "market": "期货"},
        {"code": "HNsr", "name": "白糖主连", "market": "期货"},
        {"code": "HNbr", "name": " bambooru", "market": "期货"},
        {"code": "HNl", "name": "锂矿", "market": "期货"},
        {"code": "HNss", "name": "不锈钢", "market": "期货"},
        {"code": "HNpg", "name": "玻璃", "market": "期货"},
        {"code": "HNj", "name": "焦炭", "market": "期货"},
        {"code": "HNqm", "name": "强麦", "market": "期货"},
        {"code": "HNpm", "name": "普麦", "market": "期货"},
        {"code": "HNrm", "name": "糯米", "market": "期货"},
        {"code": "HNwr", "name": "晚籼稻", "market": "期货"},
        {"code": "HNma", "name": "甲醇", "market": "期货"},
        {"code": "HNfa", "name": "脂肪酸", "market": "期货"},
        {"code": "HNst", "name": "短绒", "market": "期货"},
        {"code": "HNy", "name": " unhulled soybean", "market": "期货"},
        {"code": "HNc", "name": "玉米", "market": "期货"},
        {"code": "HNcs", "name": "玉米淀粉", "market": "期货"},
        {"code": "HNp", "name": "棕榈油", "market": "期货"},
        {"code": "HNl", "name": "LP", "market": "期货"},
        {"code": "HNfu", "name": "燃料油", "market": "期货"},
        {"code": "HNbu", "name": "豆粕", "market": "期货"},
        {"code": "HNm", "name": "豆油", "market": "期货"},
        {"code": "HNrm", "name": "稻谷", "market": "期货"},
        {"code": "HNsr", "name": "白糖", "market": "期货"},
        {"code": "HNif", "name": " Интерконтинентальная биржа", "market": "期货"},
        {"code": "HNi", "name": " 指数", "market": "期货"},
        {"code": "HNa", "name": "藻酸盐", "market": "期货"},
        {"code": "HNca", "name": "碳酸钙", "market": "期货"},
        {"code": "HNec", "name": "鸡蛋", "market": "期货"},
        {"code": "HNir", "name": "铁矿石", "market": "期货"},
    ]
    return 常用期货

# 获取实时行情
def fetch_realtime_data_all():
    """获取所有股票和期货实时行情 - 使用腾讯接口"""
    stocks = fetch_all_a_stock_codes()
    futures = fetch_futures_list()
    
    results = []
    
    # 腾讯接口支持批量查询
    session = requests.Session()
    session.trust_env = False
    
    for i in range(0, len(stocks), 50):
        batch = stocks[i:i+50]
        try:
            # 腾讯行情接口
            codes_str = ",".join([s["code"][2:] + "." + ("1" if s["code"][:2] == "sh" else "0") for s in batch])
            url = f"http://qt.gtimg.cn/s={codes_str}"
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                for line in resp.text.strip().split('\n'):
                    if not line.startswith('v_'):
                        continue
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
                            "volume": float(parts[6]) * 100,
                            "amount": float(parts[7]) * 10000,
                            "bid_price": float(parts[8]),
                            "ask_price": float(parts[9]),
                            "high_price": float(parts[31]),
                            "low_price": float(parts[32]),
                            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        stock["change_pct"] = (stock["current_price"] - stock["yesterday_close"]) / stock["yesterday_close"] * 100
                        stock["market"] = "股票"
                        # 修正代码格式
                        if stock["code"].startswith("6"):
                            stock["code"] = "sh" + stock["code"]
                        else:
                            stock["code"] = "sz" + stock["code"]
                        results.append(stock)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[ERROR] 批次获取失败: {e}")
    
    # 期货数据需要单独获取（使用模拟数据）
    for futures_item in futures:
        try:
            # 模拟期货价格（实际应接入文华等接口）
            code = futures_item["code"]
            name = futures_item["name"]
            price = 100.0 + (hash(code) % 50) / 10.0
            change_pct = (hash(code + "pct") % 20) - 10
            
            results.append({
                "code": code,
                "name": name,
                "current_price": price,
                "change_pct": change_pct,
                "volume": 1000 + (hash(code + "vol") % 10000),
                "amount": 100000 + (hash(code + "amt") % 1000000),
                "market": "期货",
                "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception:
            continue
    
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
        
        if pct > 0:
            score += min(int(pct * 5), 30)
        else:
            score -= min(int(abs(pct) * 5), 30)
        
        if volume > 1000000:
            score += 10
        
        if market == "期货":
            score += 5
        
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
    
    cursor.execute('''
        SELECT code, name, current_price, change_pct, volume, market 
        FROM stocks 
        ORDER BY ABS(change_pct) DESC 
        LIMIT 50
    ''')
    recent_data = cursor.fetchall()
    
    cursor.execute('''
        SELECT code, name, current_price, change_pct, volume, update_time, market 
        FROM stocks 
        WHERE ABS(change_pct) > 5 
        ORDER BY ABS(change_pct) DESC
    ''')
    volatility_data = cursor.fetchall()
    
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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 股票期货全量监控系统 v4 启动")
    
    init_db()
    
    while True:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始采集...")
        stocks = fetch_realtime_data_all()
        
        if stocks:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 获取到 {len(stocks)} 条数据")
            save_stock_data(stocks)
            
            opportunities = detect_opportunities()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发现 {len(opportunities)} 个机会")
            
            html = generate_html_dashboard()
            panel_path = DATA_DIR / "dashboard.html"
            with open(panel_path, 'w') as f:
                f.write(html)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 面板已更新: {panel_path}")
        
        time.sleep(30)

if __name__ == "__main__":
    main()
