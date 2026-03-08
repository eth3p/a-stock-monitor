#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股监控系统主调度程序
2026-03-04  CEO 指令完成

功能：
1. 实时行情采集（每30秒）
2. 异常检测（实时）
3. 定时任务（每天 9:25 / 15:00）
"""

import subprocess
import threading
import time
import os
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def run_script(script_name, *args):
    """运行 Python 脚本"""
    try:
        result = subprocess.run(
            ["python3", script_name] + list(args),
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.stdout:
            log(f"[{script_name}] 输出: {result.stdout[:500]}")
        if result.stderr:
            log(f"[{script_name}] 错误: {result.stderr[:500]}")
        return result.returncode == 0
    except Exception as e:
        log(f"[{script_name}] 执行失败: {e}")
        return False

def fetch_realtime_job():
    """实时行情采集任务"""
    main_script = Path(__file__).parent / "main.py"
    log("启动实时行情采集...")
    
    try:
        process = subprocess.Popen(
            ["python3", str(main_script)],
            cwd=Path(__file__).parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # 运行1小时后停止（明天继续）
        time.sleep(3600)
        process.terminate()
        process.wait()
        log("实时行情采集暂停")
        
    except KeyboardInterrupt:
        process.terminate()

def check_alerts_job():
    """提醒检查任务（每分钟）"""
    script = Path(__file__).parent / "check_alerts.py"
    log("执行提醒检查...")
    run_script(str(script))

def daily_report_job():
    """每日报告任务（9:25 / 15:00）"""
    script = Path(__file__).parent / "daily_report.py"
    log("生成每日报告...")
    run_script(str(script))

def scheduler():
    """主调度器"""
    log("股票监控系统启动")
    log(f"数据目录: {DATA_DIR}")
    log(f"日志目录: {LOG_DIR}")
    
    # 确保数据目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # 首次运行初始化
    run_script(str(Path(__file__).parent / "main.py"), "--init")
    
    # 检查是否是工作日
    today = datetime.now()
    if today.weekday() >= 5:  # 周六周日
        log("周末休市，跳过执行")
        return
    
    # 标记今日已执行报告的时间
    reported_times = set()
    
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # 每小时执行一次提醒检查
        if now.minute == 0:
            check_alerts_job()
        
        # 早盘 9:25 报告
        if current_time == "09:25" and "09:25" not in reported_times:
            daily_report_job()
            reported_times.add("09:25")
        
        # 收盘 15:00 报告
        if current_time == "15:00" and "15:00" not in reported_times:
            daily_report_job()
            reported_times.add("15:00")
        
        # 每天重置报告标记（凌晨 00:01）
        if current_time == "00:01":
            reported_times.clear()
        
        # 每30秒循环
        time.sleep(30)

if __name__ == "__main__":
    scheduler()
