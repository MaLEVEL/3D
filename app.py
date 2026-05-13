#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
彩票号码筛选工具 - 零依赖本地 Web 服务 v3
运行: python app.py
自动打开浏览器访问 http://127.0.0.1:5000
无需安装任何第三方库
"""

import http.server
import socketserver
import webbrowser
import threading
import re
import json
import os

PORT = 5000

# 读取前端页面
HTML_PAGE = ""
html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

try:
    with open(html_path, "r", encoding="utf-8") as f:
        HTML_PAGE = f.read()
except FileNotFoundError:
    print("错误: 找不到 index.html 文件")
    print("请确保 index.html 和 app.py 放在同一个文件夹里")
    exit(1)


class RequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_html(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._send_html(HTML_PAGE)
        else:
            self._send_html("<h1>404 Not Found</h1>", 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/filter":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(post_data)
                text = data.get("text", "")
                digits = data.get("digits", "")
                matches = re.findall(r"\b\d{3}\b", text)
                seen = set()
                unique = []
                for m in matches:
                    if m not in seen:
                        seen.add(m)
                        unique.append(m)
                target = set(digits)
                filtered = [n for n in unique if any(d in n for d in target)]
                self._send_json({
                    "total": len(unique),
                    "filtered": filtered,
                    "count": len(filtered),
                    "percent": round(len(filtered) / len(unique) * 100, 2) if unique else 0
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "Not Found"}, 404)


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    print("=" * 60)
    print("  彩票号码筛选工具 - 本地 Web 服务 v3")
    print("=" * 60)
    print("  服务地址: http://127.0.0.1:5000")
    print("  功能: 号码筛选 | 历史记录 | 数据保存")
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)
    threading.Timer(1.0, open_browser).start()
    with socketserver.TCPServer(("", PORT), RequestHandler) as httpd:
        httpd.serve_forever()