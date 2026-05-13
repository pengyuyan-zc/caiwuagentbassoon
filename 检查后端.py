# -*- coding: utf-8 -*-
"""检查后端 skill 加载情况"""
import requests
resp = requests.get("http://127.0.0.1:5001/api/agent/skills", timeout=5)
print(f"状态: {resp.status_code}")
import json
data = resp.json()
print(json.dumps(data, ensure_ascii=False, indent=2))
