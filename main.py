#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股监控系统 v6.1 - 数据采集优化
2026-03-08 优化完成
"""

import json
import sqlite3
import time
import os
import hashlib
import pickle
import functools
import pandas as pd
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "stocks.db"
WATCH_LIST_PATH = DATA_DIR / "watch_list.json"
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# 重试配置
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 1.5
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]

# 缓存配置
CACHE_TTL_SECONDS = 60  # 缓存60秒

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

# 创建带重试的会话
def create_session_with_retry() -> requests.Session:
    """创建带重试机制的 requests Session"""
    session = requests.Session()
    
    # 配置重试策略
    retry_strategy = Retry(
        total=MAX_RETRIES,
        read=MAX_RETRIES,
        connect=MAX_RETRIES,
        status=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=RETRY_STATUS_CODES,
        allowed_methods=["GET", "POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # 设置默认超时
    session.timeout = 15
    
    return session

# 数据缓存模块
class DataCache:
    """数据缓存管理器"""
    
    def __init__(self, cache_dir: Path, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self._session = create_session_with_retry()
    
    def _get_cache_key(self, url: str, params: Dict = None) -> str:
        """生成缓存键"""
        cache_str = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """检查缓存是否有效"""
        if not cache_file.exists():
            return False
        
        try:
            mtime = cache_file.stat().st_mtime
            return (time.time() - mtime) < self.ttl_seconds
        except:
            return False
    
    def get(self, url: str, params: Dict = None) -> Optional[Any]:
        """从缓存获取数据"""
        cache_key = self._get_cache_key(url, params)
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        
        if self._is_cache_valid(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
            except:
                return None
        return None
    
    def set(self, url: str, params: Dict, data: Any) -> None:
        """设置缓存数据"""
        cache_key = self._get_cache_key(url, params)
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            print(f"[WARN] 缓存写入失败: {e}")
    
    def clear_expired(self) -> int:
        """清理过期缓存"""
        count = 0
        for cache_file in self.cache_dir.glob("*.pkl"):
            if not self._is_cache_valid(cache_file):
                try:
                    cache_file.unlink()
                    count += 1
                except:
                    pass
        return count

# 全局缓存实例
cache_manager = DataCache(CACHE_DIR)

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

# 东方财富数据接口
def fetch_eastmoney_data():
    """
    获取东方财富数据（支持_OPTS、 complication 公开接口）
    增加重试和缓存机制
    """
    stock_codes = [
        "sh600519", "sz000858", "sh601318", "sh601888", "sz300750",
        "sh600036", "sz000651", "sh600276", "sz000333", "sh600887"
    ]
    
    # 东方财富公开数据接口（示例接口）
    # 实际使用时可能需要根据具体接口调整
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    
    # 构造请求参数
    params = {
        "pn": "1",
        "pz": "50",
        "po": "1",
        "np": "1",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152"
    }
    
    # 尝试缓存获取
    cached_data = cache_manager.get(url, params)
    if cached_data:
        print("[INFO] 从缓存获取东方财富数据")
        return parse_eastmoney_response(cached_data)
    
    try:
        session = create_session_with_retry()
        response = session.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # 缓存结果
        cache_manager.set(url, params, data)
        
        return parse_eastmoney_response(data)
        
    except Exception as e:
        print(f"[ERROR] 获取东方财富数据失败: {e}")
        return []

def parse_eastmoney_response(data: Dict) -> List[Dict]:
    """解析东方财富接口返回"""
    stocks = []
    
    try:
        if not data or "data" not in data or "diff" not in data["data"]:
            return stocks
        
        for item in data["data"]["diff"]:
            try:
                stock = {
                    "code": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "current_price": float(item.get("f2", 0)),
                    "yesterday_close": float(item.get("f18", 0)),
                    "change_pct": float(item.get("f3", 0)),
                    "volume": int(item.get("f5", 0)),
                    "amount": int(item.get("f6", 0)),
                    "open_price": float(item.get("f17", 0)),
                    "high_price": float(item.get("f15", 0)),
                    "low_price": float(item.get("f16", 0)),
                    "bid_price": float(item.get("f7", 0)),
                    "ask_price": float(item.get("f8", 0)),
                    "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                stocks.append(stock)
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"[ERROR] 解析东方财富数据失败: {e}")
    
    return stocks

# 获取 A 股实时行情（用腾讯股市接口）
def fetch_realtime_data():
    """获取所有 A 股实时行情（带重试和缓存）"""
    # 尝试从缓存获取
    url = "http://qt.gtimg.cn/s"
    params = {"codes": "sh600519,sz000858,sh601318"}  # 示例
    cached_data = cache_manager.get(url, params)
    if cached_data:
        print("[INFO] 从缓存获取腾讯实时行情")
        return cached_data
    
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
        
        # 创建会话并请求
        session = create_session_with_retry()
        resp = session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        data = parse_stock_response(resp.text)
        
        # 缓存结果
        cache_manager.set("http://qt.gtimg.cn/s", {"codes": codes_str}, data)
        
        return data
        
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

# 清理缓存函数（供外部调用）
def clear_cache():
    """清理所有缓存"""
    try:
        import shutil
        shutil.rmtree(CACHE_DIR)
        CACHE_DIR.mkdir(exist_ok=True)
        print("[INFO] 缓存已清理")
    except Exception as e:
        print(f"[ERROR] 清理缓存失败: {e}")

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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 股票监控系统 v6.1 启动")
    print(f"[INFO] 重试机制已启用: 最多 {MAX_RETRIES} 次重试")
    print(f"[INFO] 数据缓存已启用: TTL {CACHE_TTL_SECONDS} 秒")
    
    # 初始化
    init_db()
    watch_list = init_watch_list()
    
    # 清理过期缓存
    expired_count = cache_manager.clear_expired()
    if expired_count > 0:
        print(f"[INFO] 清理了 {expired_count} 个过期缓存文件")
    
    # 实时监控循环
    while True:
        # 尝试获取东方财富数据（优先）
        stocks = fetch_eastmoney_data()
        
        # 如果东方财富数据获取失败，尝试腾讯数据
        if not stocks:
            print("[INFO] 东方财富数据获取失败，尝试腾讯数据")
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
