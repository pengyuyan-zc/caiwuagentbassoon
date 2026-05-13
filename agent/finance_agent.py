# -*- coding: utf-8 -*-
"""
财务智能体 - LangGraph ReAct Agent 入口

架构：
  LangGraph StateGraph → ReAct 循环
    tools_call → execute_tool → tool_result → tools_call / END

使用方式：
    # 启动服务
    python -m agent.server

    # 导入使用
    from agent.finance_agent import create_react_agent, invoke_skill, list_skills

    result = create_react_agent().invoke({
        "messages": [{"role": "user", "content": "帮我生成开票凭证"}]
    })
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# ── 路径配置 ──────────────────────────────────────────────────────────────

_CURRENT_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _CURRENT_FILE.parent.parent
_API_DIR = _PROJECT_ROOT / "api"
_SKILLS_DIR = _CURRENT_FILE.parent / "skills"      # 改成 agent/skills/

# 将路径加入 sys.path
_root_str = str(_PROJECT_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)
_skills_str = str(_SKILLS_DIR)
if _skills_str not in sys.path:
    sys.path.insert(0, _skills_str)

# ── 加载 .env ────────────────────────────────────────────────────────────

def _load_env():
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

_load_env()

# ── 从 helpers 导出所有公共 API ─────────────────────────────────────────

from agent.helpers import (
    list_skills,
    invoke_skill,
    _build_skill_system_prompt,
    _load_tools_from_skills,
    _call_dashscope,
    DASHSCOPE_API_KEY,
    DASHSCOPE_API_URL,
    DEFAULT_MODEL,
    MAX_LOOP,
    _SKILLS_DIR,
)

# ══════════════════════════════════════════════════════════════════════════
# LangGraph 版本检测
# ══════════════════════════════════════════════════════════════════════════

def is_langgraph_available() -> bool:
    try:
        from langgraph.graph import StateGraph, END
        return True
    except ImportError:
        return False


# ══════════════════════════════════════════════════════════════════════════
# Agent 创建工厂
# ══════════════════════════════════════════════════════════════════════════

def create_react_agent(
    model: str = DEFAULT_MODEL,
    api_key: str = DASHSCOPE_API_KEY,
    api_url: str = DASHSCOPE_API_URL,
    max_loop: int = MAX_LOOP,
    use_v2: bool = False,
):
    """
    创建 ReAct Agent，自动选择 LangGraph（如果已安装）或纯 Python 实现。

    Args:
        model: LLM 模型名称
        api_key: DashScope API Key
        api_url: DashScope API URL
        max_loop: 最大循环次数
        use_v2: 是否使用 v2 多节点工作流（支持人工审批、checkpoint 持久化）
    """
    if is_langgraph_available():
        if use_v2:
            from agent.graph_v2 import create_react_agent_v2
            return create_react_agent_v2(
                model=model,
                api_key=api_key,
                api_url=api_url,
                max_loop=max_loop,
            )
        else:
            from agent.graph import create_langgraph_agent
            return create_langgraph_agent(
                model=model,
                api_key=api_key,
                api_url=api_url,
                max_loop=max_loop,
            )
    else:
        from agent.react_simple import create_simple_agent
        return create_simple_agent(
            model=model,
            api_key=api_key,
            api_url=api_url,
            max_loop=max_loop,
        )


# ── 直接运行入口 ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="财务智能体 - LangGraph ReAct Agent")
    parser.add_argument("--server", action="store_true", help="启动 FastAPI 服务")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM 模型（默认: {DEFAULT_MODEL}）")
    args = parser.parse_args()

    print("=" * 60)
    print("  财务智能体 - LangGraph ReAct Agent")
    print("=" * 60)
    print(f"  Skills 目录 : {_SKILLS_DIR}")
    print(f"  模型        : {args.model}")
    print("  LangGraph   : %s" % ("已安装" if is_langgraph_available() else "未安装，将使用纯 Python ReAct"))
    print("")
    print("  可用 Skills:")
    for s in list_skills():
        print("    - %s  %s" % (s["name"], s["description"] or ""))
    print(f"\n  启动服务:")
    print("    python -m agent.server")
    print("=" * 60)

    if args.server:
        from agent.server import run_server
        run_server(model=args.model)
