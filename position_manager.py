#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
仓位管理模块 - A股监控系统 v6.1
2026-03-08 仓位管理模块
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class StockPosition:
    """股票仓位数据类"""
    code: str
    name: str
    shares: int
    cost_price: float
    current_price: float
    market_value: float
    gain_loss: float
    gain_loss_pct: float
    last_update: str
    
    def is_stop_loss_triggered(self, stop_loss_threshold: float = 0.10) -> bool:
        """检查是否触发止损提示"""
        return self.gain_loss_pct <= -stop_loss_threshold


class PositionManager:
    """仓位管理器"""
    
    # 配置参数
    MAX_POSITION_RATIO = 0.50  # 最大仓位限制：50%
    MAX_STOCK_POSITION_RATIO = 0.20  # 单票最大仓位：20%
    STOP_LOSS_THRESHOLD = 0.10  # 止损提示：单票亏损>10%触发提醒
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)
        self.db_path = data_dir / "position.db"
        self.positions: Dict[str, StockPosition] = {}
        self.total_equity = 0.0  # 总资金
        self.total_position_value = 0.0  # 总仓位市值
        self._load_positions()
    
    def _load_positions(self):
        """加载历史仓位数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建仓位表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                code TEXT PRIMARY KEY,
                name TEXT,
                shares INTEGER,
                cost_price REAL,
                current_price REAL,
                market_value REAL,
                gain_loss REAL,
                gain_loss_pct REAL,
                last_update TEXT
            )
        ''')
        
        # 创建资金流水表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                transaction_type TEXT,
                shares INTEGER,
                price REAL,
                amount REAL,
                timestamp TEXT
            )
        ''')
        
        # 创建账户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY,
                total_equity REAL,
                position_ratio REAL,
                last_update TEXT
            )
        ''')
        
        conn.commit()
        
        # 加载当前仓位
        cursor.execute('SELECT * FROM positions')
        rows = cursor.fetchall()
        for row in rows:
            position = StockPosition(
                code=row[0],
                name=row[1],
                shares=row[2],
                cost_price=row[3],
                current_price=row[4],
                market_value=row[5],
                gain_loss=row[6],
                gain_loss_pct=row[7],
                last_update=row[8]
            )
            self.positions[position.code] = position
        
        # 加载账户数据
        cursor.execute('SELECT * FROM account ORDER BY id DESC LIMIT 1')
        account_row = cursor.fetchone()
        if account_row:
            self.total_equity = account_row[1]
            self.total_position_value = self.total_equity * account_row[2] if account_row[2] else 0.0
        
        conn.close()
    
    def _save_account(self):
        """保存账户数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        position_ratio = self.total_position_value / self.total_equity if self.total_equity > 0 else 0.0
        
        cursor.execute('''
            INSERT OR REPLACE INTO account (id, total_equity, position_ratio, last_update)
            VALUES (1, ?, ?, ?)
        ''', (self.total_equity, position_ratio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        conn.commit()
        conn.close()
    
    def _save_position(self, position: StockPosition):
        """保存仓位数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO positions 
            (code, name, shares, cost_price, current_price, market_value, gain_loss, gain_loss_pct, last_update)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (position.code, position.name, position.shares, position.cost_price,
              position.current_price, position.market_value, position.gain_loss,
              position.gain_loss_pct, position.last_update))
        
        conn.commit()
        conn.close()
    
    def _save_transaction(self, code: str, trans_type: str, shares: int, price: float, amount: float):
        """保存交易流水"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO transactions (code, transaction_type, shares, price, amount, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (code, trans_type, shares, price, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        conn.commit()
        conn.close()
    
    def update_account(self, total_equity: float):
        """更新总资金"""
        self.total_equity = total_equity
        self._save_account()
    
    def update_stock_price(self, code: str, current_price: float, name: str = "") -> Optional[StockPosition]:
        """更新股票价格并计算盈亏"""
        if code not in self.positions:
            return None
        
        position = self.positions[code]
        position.current_price = current_price
        position.market_value = position.shares * current_price
        position.gain_loss = position.market_value - (position.shares * position.cost_price)
        position.gain_loss_pct = position.gain_loss / (position.shares * position.cost_price) if (position.shares * position.cost_price) > 0 else 0.0
        position.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self._save_position(position)
        
        return position
    
    def add_position(self, code: str, name: str, shares: int, cost_price: float, current_price: float = None) -> bool:
        """增加仓位"""
        if current_price is None:
            current_price = cost_price
        
        market_value = shares * current_price
        gain_loss = market_value - (shares * cost_price)
        gain_loss_pct = gain_loss / (shares * cost_price) if (shares * cost_price) > 0 else 0.0
        
        # 检查单票仓位限制
        if self.total_equity > 0:
            stock_position_ratio = market_value / self.total_equity
            if stock_position_ratio > self.MAX_STOCK_POSITION_RATIO:
                print(f"[WARNING] {code} {name} 仓位 {stock_position_ratio:.2%} 超过单票上限 {self.MAX_STOCK_POSITION_RATIO:.2%}")
                return False
        
        # 检查总仓位限制
        new_total_position_value = self.total_position_value + market_value
        if self.total_equity > 0:
            new_position_ratio = new_total_position_value / self.total_equity
            if new_position_ratio > self.MAX_POSITION_RATIO:
                print(f"[WARNING] 总仓位 {new_position_ratio:.2%} 超过上限 {self.MAX_POSITION_RATIO:.2%}")
                return False
        
        position = StockPosition(
            code=code,
            name=name,
            shares=shares,
            cost_price=cost_price,
            current_price=current_price,
            market_value=market_value,
            gain_loss=gain_loss,
            gain_loss_pct=gain_loss_pct,
            last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        self.positions[code] = position
        self.total_position_value = new_total_position_value
        self._save_position(position)
        self._save_transaction(code, "BUY", shares, cost_price, market_value)
        
        print(f"[INFO] 已建仓: {code} {name} x {shares} @ {cost_price:.2f}")
        return True
    
    def reduce_position(self, code: str, shares: int, current_price: float) -> bool:
        """减仓"""
        if code not in self.positions:
            print(f"[ERROR] {code} 仓位不存在")
            return False
        
        position = self.positions[code]
        if shares > position.shares:
            print(f"[ERROR] 减仓数量 {shares} 超过持仓 {position.shares}")
            return False
        
        # 更新仓位
        position.shares -= shares
        position.market_value = position.shares * current_price
        position.gain_loss = position.market_value - (position.shares * position.cost_price)
        position.gain_loss_pct = position.gain_loss / (position.shares * position.cost_price) if (position.shares * position.cost_price) > 0 else 0.0
        position.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 如果仓位清零，移除仓位
        if position.shares == 0:
            del self.positions[code]
            self.total_position_value -= (position.market_value + shares * current_price)
        else:
            self.positions[code] = position
            self.total_position_value -= (shares * current_price)
        
        self._save_position(position)
        self._save_transaction(code, "SELL", shares, current_price, shares * current_price)
        
        print(f"[INFO] 已减仓: {code} -{shares} @ {current_price:.2f}")
        return True
    
    def close_position(self, code: str, current_price: float) -> bool:
        """清仓"""
        if code not in self.positions:
            print(f"[ERROR] {code} 仓位不存在")
            return False
        
        position = self.positions[code]
        shares = position.shares
        self._save_transaction(code, "SELL", shares, current_price, shares * current_price)
        
        del self.positions[code]
        self.total_position_value -= (shares * current_price)
        
        print(f"[INFO] 已清仓: {code} {position.name} x {shares} @ {current_price:.2f}")
        return True
    
    def get_position(self, code: str) -> Optional[StockPosition]:
        """获取仓位信息"""
        return self.positions.get(code)
    
    def get_all_positions(self) -> Dict[str, StockPosition]:
        """获取所有仓位"""
        return self.positions
    
    def check_stop_loss(self) -> List[Tuple[str, StockPosition]]:
        """检查止损提示"""
        stop_loss_stocks = []
        for code, position in self.positions.items():
            if position.is_stop_loss_triggered(self.STOP_LOSS_THRESHOLD):
                stop_loss_stocks.append((code, position))
        return stop_loss_stocks
    
    def get_position_summary(self) -> dict:
        """获取仓位汇总"""
        total_gain_loss = sum(p.gain_loss for p in self.positions.values())
        total_gain_loss_pct = total_gain_loss / self.total_position_value if self.total_position_value > 0 else 0.0
        
        return {
            "总资金": self.total_equity,
            "总仓位市值": self.total_position_value,
            "总仓位比例": f"{self.total_position_value / self.total_equity:.2%}" if self.total_equity > 0 else "0%",
            "持仓数量": len(self.positions),
            "总盈亏": total_gain_loss,
            "总收益率": f"{total_gain_loss_pct:.2%}",
            "仓位详情": {code: {
                "名称": p.name,
                "持股数": p.shares,
                "成本价": p.cost_price,
                "当前价": p.current_price,
                "市值": p.market_value,
                "盈亏": p.gain_loss,
                "收益率": f"{p.gain_loss_pct:.2%}"
            } for code, p in self.positions.items()}
        }
    
    def generate_html_report(self) -> str:
        """生成HTML仓位报告"""
        summary = self.get_position_summary()
        
        status = "✅ 健康"
        if summary["总仓位比例"] != "0%":
            ratio = float(summary["总仓位比例"].strip('%')) / 100
            if ratio > self.MAX_POSITION_RATIO:
                status = "⚠️ 超仓"
            elif ratio > self.MAX_STOCK_POSITION_RATIO * 2:
                status = "🚨 高风险"
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>仓位管理报告</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background: #1e1e2e; color: #cdd6f4; margin: 0; padding: 20px; }}
        h1 {{ color: #89b4fa; margin-bottom: 20px; }}
        .status {{ padding: 10px 20px; border-radius: 8px; margin-bottom: 20px; font-weight: bold; }}
        .status健康 {{ background: #1e1e2e; color: #a6e3a1; }}
        .status⚠️ {{ background: #1e1e2e; color: #f9e2af; }}
        .status🚨 {{ background: #1e1e2e; color: #f38ba8; }}
        .panel {{ background: #313244; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .panel h2 {{ color: #f38ba8; border-bottom: 1px solid #45475a; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #45475a; }}
        th {{ background: #45475a; color: #f5e0dc; }}
        .trending-up {{ color: #a6e3a1; }}
        .trending-down {{ color: #f38ba8; }}
        .stop-loss {{ background: #452a2a; }}
        .summary-item {{ display: inline-block; margin: 10px 20px; }}
        .summary-value {{ color: #89b4fa; font-weight: bold; font-size: 18px; }}
    </style>
</head>
<body>
    <h1>📊 仓位管理报告</h1>
    
    <div class="status {status.replace(' ', '')}">状态: {status}</div>
    
    <div class="panel">
        <h2>📈 账户概览</h2>
        <div class="summary-item">总资金: <span class="summary-value">{summary['总资金']:,.2f}</span></div>
        <div class="summary-item">总仓位: <span class="summary-value">{summary['总仓位市值']:,.2f}</span></div>
        <div class="summary-item">仓位比例: <span class="summary-value">{summary['总仓位比例']}</span></div>
        <div class="summary-item">持仓数量: <span class="summary-value">{summary['持仓数量']}</span></div>
        <div class="summary-item">总盈亏: <span class="summary-value {'trending-up' if summary['总盈亏'] >= 0 else 'trending-down'}">{summary['总盈亏']:,.2f}</span></div>
        <div class="summary-item">总收益率: <span class="summary-value {'trending-up' if summary['总收益率'].strip('%') >= '0' else 'trending-down'}">{summary['总收益率']}</span></div>
    </div>
    
    <div class="panel">
        <h2>📋 持仓明细</h2>
        <table>
            <tr><th>代码</th><th>名称</th><th>持股数</th><th>成本价</th><th>当前价</th><th>市值</th><th>盈亏</th><th>收益率</th></tr>
"""
        
        for code, detail in summary['仓位详情'].items():
            gain_loss = float(detail['盈亏'])
            gain_loss_pct = float(detail['收益率'].strip('%'))
            
            gain_loss_class = ""
            if gain_loss_pct < -10:
                gain_loss_class = "stop-loss"
            
            gain_loss_color = "trending-up" if gain_loss >= 0 else "trending-down"
            
            html += f"""
            <tr class="{gain_loss_class}">
                <td>{code}</td>
                <td>{detail['名称']}</td>
                <td>{detail['持股数']}</td>
                <td>{detail['成本价']:.2f}</td>
                <td>{detail['当前价']:.2f}</td>
                <td>{detail['市值']:,.2f}</td>
                <td class="{gain_loss_color}">{gain_loss:,.2f}</td>
                <td class="{gain_loss_color}">{detail['收益率']}</td>
            </tr>"""
        
        html += """</table></div>
        
        <div class="panel">
            <h2>⚠️ 止损提示</h2>
            <ul>
"""
        
        stop_loss_positions = self.check_stop_loss()
        if stop_loss_positions:
            for code, position in stop_loss_positions:
                html += f"""
                <li class="trending-down">
                    <strong>{code} {position.name}</strong> 
                    亏损 {position.gain_loss_pct:.2%} - 触发止损提示!
                </li>"""
        else:
            html += """
                <li class="trending-up">当前无触发止损提示的持仓</li>"""
        
        html += """
            </ul>
        </div>
    </body>
</html>"""
        
        return html


# 全局实例
_position_manager: Optional[PositionManager] = None


def get_position_manager(data_dir: Path) -> PositionManager:
    """获取全局仓位管理器实例"""
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager(data_dir)
    return _position_manager


def init_position_manager(data_dir: Path) -> PositionManager:
    """初始化仓位管理器"""
    global _position_manager
    _position_manager = PositionManager(data_dir)
    return _position_manager
