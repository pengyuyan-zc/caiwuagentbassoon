# 财务智能体 - LangGraph ReAct Agent    启动前端： npm run dev   启动后端：& D:/xuexi/anaconda/python.exe f:/xiangmu/pythonProject6（ruibo）/invoice-tax-agent/开票主体税务凭证生成.py

基于 **LangGraph** 框架搭建的 **ReAct 智能体**，动态加载 Skills 技能工具，前端使用 Vue + Nuxt 展示聊天界面。

## 架构

```
用户输入 → LangGraph ReAct Agent → LLM (qwen-turbo)
                                    ↓
                              意图识别
                                    ↓
                         ┌──────────┴──────────┐
                         ↓                      ↓
                   不需要工具              需要调用工具
                   → 直接回复              → 执行 Skill
                                                 ↓
                                    ┌───────────┼───────────┐
                                    ↓           ↓           ↓
                              invoice-    salary-     (未来扩展)
                              voucher     voucher
```

## 目录结构

```
财务智能体/
├── agent/                         # Python Agent 核心
│   ├── __init__.py
│   ├── finance_agent.py           # 入口，Agent 工厂
│   ├── graph.py                   # LangGraph ReAct 图
│   ├── react_simple.py            # 纯 Python ReAct（LangGraph 未安装时）
│   ├── helpers.py                 # 共享工具函数
│   ├── server.py                  # FastAPI 服务
│   └── __pycache__/
│
├── web/                           # Vue + Nuxt 前端
│   ├── pages/index.vue            # 聊天主页面
│   ├── components/                # 组件
│   ├── assets/css/main.css        # 样式
│   ├── nuxt.config.ts
│   └── package.json
│
├── uploads/                       # 上传文件目录（自动创建）
├── requirements.txt               # Python 依赖
├── .env                          # 环境配置（API Key 等）
├── 启动全部.bat                   # 一键启动前后端
└── 启动后端.bat                   # 仅启动后端
```

## 快速启动

### 1. 安装 Python 依赖

```bash
cd F:\xiangmu\pythonProject6（ruibo）\财务智能体
pip install -r requirements.txt
```

### 2. 配置 API Key

编辑 `.env` 文件，填入您的阿里云 DashScope API Key：

```
DASHSCOPE_API_KEY=sk-your-key-here
LLM_MODEL=qwen-turbo   # 可选: qwen-turbo, qwen-plus, qwen-max
```

### 3. 启动服务

**方式一：一键启动（推荐）**
```bash
启动全部.bat
```

**方式二：分别启动**

```bash
# 终端 1 - 启动后端
python -m agent.server

# 终端 2 - 启动前端
cd web
npm install   # 首次运行需要
npm run dev
```

### 4. 访问

- 前端界面：http://localhost:3000
- 后端 API：http://127.0.0.1:5001
- API 文档：http://127.0.0.1:5001/docs

## 添加新 Skill

将新技能放到 `F:\xiangmu\pythonProject6（ruibo）\skills\` 目录下：

```
skills/
└── my-new-skill/           # Skill 名称
    ├── SKILL.md            # 技能描述（LLM 据此理解何时调用）
    └── agent.py            # 执行逻辑 + TOOLS 定义
```

### SKILL.md 格式

```markdown
---
name: my-new-skill
description: 简短描述，触发词
---

# 我的新技能

当用户请求 XXX 时，立即使用此 skill。

调用方式：
```python
from my_new_skill import my_function
result = my_function(param="xxx")
```

返回：...
```

### agent.py 格式

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

def my_function(param: str) -> dict:
    """技能实现"""
    return {"success": True, "result": param}

# ──────────────────────────────────────────────
# 工具元数据（必须，LLM 据此调用）
# ──────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "my_function",
            "description": "做什么的...",
            "parameters": {
                "type": "object",
                "properties": {
                    "param": {"type": "string", "description": "参数说明"}
                },
                "required": ["param"]
            }
        }
    }
]
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查，查看已加载 Skills |
| `/api/agent/skills` | GET | 列出所有可用 Skills |
| `/api/agent/chat` | POST | 对话（支持文件上传） |
| `/api/agent/chat/stream` | POST | 流式对话（实时输出） |
| `/download?file=xxx` | GET | 下载生成的文件 |

## 当前已加载 Skills

| Skill | 触发词 | 说明 |
|-------|--------|------|
| `invoice-tax-voucher` | 生成开票凭证、X月开票凭证 | 根据金蝶云格式 Excel 自动生成凭证 |

## 技术选型

| 组件 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph（已安装）/ 纯 Python（未安装） | 自动降级 |
| LLM | 阿里云 DashScope (qwen-turbo) | OpenAI 兼容 API |
| 后端服务 | FastAPI + Uvicorn | 高性能异步 API |
| 前端 | Nuxt 3 + Vue 3 | SSR + SPA 双模式 |
| 工具注册 | 动态加载 agent.py 的 TOOLS | 按需加载 |
