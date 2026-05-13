# -*- coding: utf-8 -*-
"""
人工审批节点

提供审批状态序列化和前端预览数据结构。
审批流程通过 server.py 的 /api/agent/approve 接口驱动。
"""

from __future__ import annotations

from typing import TypedDict, Optional, Literal
from agent import config


# ══════════════════════════════════════════════════════════════════════════
# 审批数据序列化
# ══════════════════════════════════════════════════════════════════════════

def build_approval_preview(state: dict) -> dict:
    """
    从 AgentState 构建前端审批预览数据。

    返回格式：
        {
            "session_id": "xxx",
            "step": 1,
            "current_node": "human_approval",
            "voucher_summary": {
                "count": 15,
                "line_count": 45,
                "output_file": "...",
            },
            "tool_results": [...],
            "last_message": "凭证已生成，共15张...",
        }
    """
    tool_results = state.get("tool_results", [])
    messages = state.get("messages", [])

    # 提取凭证摘要
    voucher_summary = None
    for tr in reversed(tool_results):
        result = tr.get("result", {})
        if isinstance(result, dict) and result.get("output_file"):
            voucher_summary = {
                "count": result.get("voucher_count", 0),
                "line_count": result.get("line_count", 0),
                "output_file": result.get("output_file", ""),
                "message": result.get("message", ""),
                "tool": tr.get("tool", ""),
            }
            break

    # 提取最后一条 assistant 消息
    last_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            last_msg = msg["content"]
            break

    # 提取已使用的工具
    tools_used = []
    for tr in tool_results:
        if tr.get("tool"):
            tools_used.append(tr["tool"])

    return {
        "step": state.get("step", 0),
        "finished": state.get("finished", False),
        "waiting_for_approval": state.get("waiting_for_approval", False),
        "current_node": state.get("current_node", ""),
        "voucher_summary": voucher_summary,
        "tools_used": list(dict.fromkeys(tools_used)),
        "tool_results_count": len(tool_results),
        "last_message": last_msg,
    }


def is_approval_required(state: dict) -> bool:
    """
    判断当前状态是否需要人工审批。

    条件：
      1. human_approval.enabled = True
      2. 上一步有凭证生成工具调用
      3. 且 finished = False（即 LLM 没有直接回复）
    """
    if not config.human_approval.enabled:
        return False
    if not config.human_approval.force_for_vouchers:
        return False

    tool_results = state.get("tool_results", [])
    if not tool_results:
        return False

    last_tool = tool_results[-1].get("tool", "")
    is_voucher_tool = any(kw in last_tool.lower() for kw in ["voucher", "invoice", "management_voucher"])

    return is_voucher_tool and not state.get("finished", True)


# ══════════════════════════════════════════════════════════════════════════
# 审批记录（用于审计）
# ══════════════════════════════════════════════════════════════════════════

def log_approval(session_id: str, action: str, approval_data: dict, user_id: str = "default") -> None:
    """
    记录审批操作到 session 数据库（审计日志）。
    """
    from agent import config as _cfg
    _cfg.log_session_event(
        session_id,
        "approval",
        {
            "action": action,
            "approval_data": approval_data,
            "user_id": user_id,
        }
    )
