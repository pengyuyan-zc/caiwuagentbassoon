# -*- coding: utf-8 -*-
"""
Agent 共享工具函数（helpers）

被 graph.py、react_simple.py、finance_agent.py 共同使用，
避免循环 import。
"""

from __future__ import annotations

import os
import json
import requests
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════════════════════
# 全局配置（从 config.py 导入，消除硬编码）
# ══════════════════════════════════════════════════════════════════════════

_CURRENT_DIR = Path(__file__).parent.resolve()           # agent/
_PROJECT_ROOT = _CURRENT_DIR.parent                        # 财务智能体/
_SKILLS_DIR = _CURRENT_DIR / "skills"                    # agent/skills/

# 从 config 模块导入配置（统一管理）
from agent import config as _config

DASHSCOPE_API_KEY = _config.dashscope.api_key
DASHSCOPE_API_URL = _config.dashscope.api_url
DEFAULT_MODEL = _config.agent.model
MAX_LOOP = _config.agent.max_loop


# ══════════════════════════════════════════════════════════════════════════
# Skill 管理
# ══════════════════════════════════════════════════════════════════════════

def list_skills(skills_dir: Optional[Path] = None) -> list[dict]:
    """列出所有可用 Skills"""
    _dir = Path(skills_dir) if skills_dir else _SKILLS_DIR
    if not _dir.exists():
        return []
    result = []
    for item in _dir.iterdir():
        if item.is_dir() and not item.name.startswith("_") and not item.name.startswith("."):
            skill_md = item / "SKILL.md"
            agent_py = item / "agent.py"
            if skill_md.exists() or agent_py.exists():
                result.append({
                    "name": item.name,
                    "path": str(item),
                    "description": _read_skill_description(skill_md) if skill_md.exists() else ""
                })
    return result


def _read_skill_description(skill_md: Path) -> str:
    """从 SKILL.md 读取 description 字段（支持 YAML frontmatter 格式）"""
    try:
        import re
        text = skill_md.read_text(encoding="utf-8")
        match = re.search(r'^description:\s*(.+)$', text, re.MULTILINE)
        if match:
            return match.group(1).strip().strip('"').strip("'")
        return ""
    except Exception:
        return ""


def invoke_skill(skill_name: str, **kwargs) -> dict:
    """直接调用指定 skill（绕过 LLM），始终返回 dict"""
    skill_dir = _SKILLS_DIR / skill_name
    agent_py = skill_dir / "agent.py"
    if not agent_py.exists():
        return {
            "success": False,
            "message": f"未找到 skill: {skill_name}，可用: {[s['name'] for s in list_skills()]}"
        }

    import importlib.util
    spec = importlib.util.spec_from_file_location(f"skill_{skill_name}_agent", str(agent_py))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 直接找 invoke_ 开头的工具函数
    tool_name = f"invoke_{skill_name.replace('-', '_')}"
    if hasattr(mod, tool_name):
        fn = getattr(mod, tool_name)
        try:
            result = fn(**kwargs)
            # agent.py 的工具函数返回 JSON 字符串，需要解析为 dict
            if isinstance(result, str):
                import json
                return json.loads(result)
            return result
        except Exception as e:
            import traceback
            return {"success": False, "message": f"{e}\n{traceback.format_exc()}"}

    return {"success": False, "message": f"skill '{skill_name}' 没有找到工具函数 {tool_name}"}


def _build_skill_system_prompt(skills_paths: Optional[list[Path]] = None) -> str:
    """读取所有 SKILL.md，拼成 LLM 的系统提示词。"""
    _paths = skills_paths or [_SKILLS_DIR]
    parts = []
    for sp in _paths:
        skill_dir = Path(sp).resolve()
        if not skill_dir.exists():
            continue
        for item in skill_dir.iterdir():
            if not (item.is_dir() and not item.name.startswith("_") and not item.name.startswith(".")):
                continue
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                parts.append(f"\n\n=== Skill: {item.name} ===\n")
                parts.append(skill_md.read_text(encoding="utf-8"))

    if not parts:
        return "你是一个专业的财务助手。"
    header = (
        "你是一个专业的财务助手，以下是你可用的技能（Skills）：\n"
        "当用户请求涉及某个技能时，请调用对应的工具函数。\n"
        "工具调用的参数必须严格按照工具描述中的格式提供。\n"
        "【重要规则】当工具返回 success=false 时，必须直接将工具中的 message 内容作为最终回复告知用户，"
        "不要自行猜测原因或建议其他操作。\n"
    )
    return header + "".join(parts)


def _load_tools_from_skills(skills_paths: Optional[list[Path]] = None) -> list:
    """从所有 agent.py 加载 TOOLS 定义。"""
    _paths = skills_paths or [_SKILLS_DIR]
    all_tools = []
    for sp in _paths:
        skill_dir = Path(sp).resolve()
        if not skill_dir.exists():
            continue
        for item in skill_dir.iterdir():
            if not (item.is_dir() and not item.name.startswith("_") and not item.name.startswith(".")):
                continue
            agent_py = item / "agent.py"
            if not agent_py.exists():
                continue
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"skill_{item.name}_agent", str(agent_py))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "TOOLS"):
                all_tools.extend(mod.TOOLS)
                import sys as _sys
                _sys.stderr.write(
                    f"[Agent] 已加载 skill '{item.name}'，"
                    f"工具: {[t['function']['name'] for t in mod.TOOLS]}\n"
                )
                _sys.stderr.flush()
    return all_tools


def _call_dashscope(
    messages: list[dict],
    tools: list,
    api_key: str,
    api_url: str,
    model: str = "qwen-turbo",
) -> dict:
    """调用 DashScope API"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    if tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "parameters": t["function"]["parameters"],
                }
            }
            for t in tools
        ]

    resp = requests.post(api_url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    result = resp.json()
    import sys as _sys_stderr
    _sys_stderr.stderr.write(f"[dashscope] 请求完成，choices 数: {len(result.get('choices', []))}\n")
    _sys_stderr.stderr.flush()

    if "error" in result:
        raise RuntimeError(f"API错误: {result['error']}")
    if "choices" not in result or not result["choices"]:
        raise RuntimeError(f"API返回异常: {result}")

    return result["choices"][0]["message"]
