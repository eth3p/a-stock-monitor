#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可视化面板服务 - CEO Task #002
2026-03-04 23:55 升级
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.path = "/dashboard.html"
        return super().do_GET()

def start_dashboard_server(port=8080):
    """启动可视化面板服务"""
    os.chdir(DATA_DIR)
    server = HTTPServer(('0.0.0.0', port), DashboardHandler)
    print(f"📊 监控面板已启动: http://localhost:{port}")
    print(f"📁 数据目录: {DATA_DIR}")
    server.serve_forever()

if __name__ == "__main__":
    start_dashboard_server()
