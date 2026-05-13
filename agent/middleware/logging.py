# -*- coding: utf-8 -*-
"""
结构化日志中间件

功能：
  1. 节点状态变更日志（每个节点输入/输出）
  2. 执行轨迹（按 session_id + step 记录）
  3. 可选 LangSmith 集成

使用方式：
    from agent.middleware.logging import setup_logging, log_node_transition

    setup_logging()
    log_node_transition("model_node", before_state, after_state)
"""

from __future__ import annotations

import sys
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from agent import config


# ══════════════════════════════════════════════════════════════════════════
# 日志配置
# ══════════════════════════════════════════════════════════════════════════

LOG_DIR = config._PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

_loggers: dict = {}


def _get_logger(name: str) -> logging.Logger:
    """获取或创建 logger"""
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # 文件 handler（每天一个日志文件）
        today = datetime.now().strftime("%Y%m%d")
        fh = logging.FileHandler(
            LOG_DIR / f"finance_agent_{today}.log",
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)

        # 控制台 handler
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.INFO)

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        fh.setFormatter(fmt)
        ch.setFormatter(fmt)

        logger.addHandler(fh)
        logger.addHandler(ch)

    _loggers[name] = logger
    return logger


# ══════════════════════════════════════════════════════════════════════════
# 节点状态变更日志
# ══════════════════════════════════════════════════════════════════════════

def log_node_transition(
    node_name: str,
    before_state: dict,
    after_state: dict,
    session_id: str = "unknown",
) -> None:
    """
    记录节点状态转换。

    记录内容：
      - node_name: 节点名称
      - session_id: 会话 ID
      - step: 当前步数
      - transition_type: 状态变化类型
      - delta: 状态变化量（messages 数量变化、tool_results 变化等）
    """
    logger = _get_logger("node_transition")

    # 计算状态变化量
    before_msgs = len(before_state.get("messages", []))
    after_msgs = len(after_state.get("messages", []))
    before_tools = len(before_state.get("tool_results", []))
    after_tools = len(after_state.get("tool_results", []))
    before_step = before_state.get("step", 0)
    after_step = after_state.get("step", 0)

    delta = {
        "messages_delta": after_msgs - before_msgs,
        "tool_results_delta": after_tools - before_tools,
        "step_delta": after_step - before_step,
        "finished_changed": before_state.get("finished") != after_state.get("finished"),
        "waiting_for_approval": after_state.get("waiting_for_approval", False),
    }

    # 提取关键信息
    last_msg_role = None
    last_msg_content = ""
    if after_state.get("messages"):
        last = after_state["messages"][-1]
        last_msg_role = last.get("role")
        content = last.get("content", "")
        last_msg_content = content[:100] + "..." if len(content) > 100 else content

    log_entry = {
        "ts": datetime.now().isoformat(),
        "node": node_name,
        "session_id": session_id,
        "step": after_step,
        "delta": delta,
        "last_msg_role": last_msg_role,
        "last_msg_preview": last_msg_content,
        "waiting_approval": after_state.get("waiting_for_approval", False),
        "approval_data_keys": list(after_state.get("approval_data", {}).keys()) if after_state.get("approval_data") else None,
    }

    logger.info(
        f"[{node_name}] step={after_step} "
        f"msgs+{delta['messages_delta']} tools+{delta['tool_results_delta']} "
        f"waiting={delta['waiting_for_approval']} "
        f"last_role={last_msg_role}"
    )

    # 写入 session trace
    try:
        from agent import config as _cfg
        _cfg.log_session_event(
            session_id,
            f"node_{node_name}",
            log_entry,
        )
    except Exception:
        pass  # 非关键路径，日志失败不影响主流程

    # 持久化详细日志到文件
    try:
        log_file = LOG_DIR / f"trace_{session_id}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
# 工具调用日志
# ══════════════════════════════════════════════════════════════════════════

def log_tool_call(
    tool_name: str,
    args: dict,
    result: dict,
    duration_ms: float,
    session_id: str = "unknown",
) -> None:
    """记录工具调用（参数 + 结果 + 耗时）"""
    logger = _get_logger("tool_call")

    success = result.get("success", False) if isinstance(result, dict) else None
    output_file = result.get("output_file", "") if isinstance(result, dict) else ""
    error_msg = result.get("message", "")[:100] if isinstance(result, dict) else ""

    logger.info(
        f"[tool:{tool_name}] "
        f"success={success} "
        f"duration={duration_ms:.0f}ms "
        f"output={output_file[:60]}..."
    )

    try:
        from agent import config as _cfg
        _cfg.log_session_event(
            session_id,
            "tool_call",
            {
                "tool": tool_name,
                "args": args,
                "success": success,
                "duration_ms": duration_ms,
                "output_file": output_file,
                "error": error_msg,
            },
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
# LLM 调用日志
# ══════════════════════════════════════════════════════════════════════════

def log_llm_call(
    model: str,
    messages_count: int,
    tools_count: int,
    has_tool_calls: bool,
    duration_ms: float,
    session_id: str = "unknown",
    error: str = None,
) -> None:
    """记录 LLM 调用（输入输出）"""
    logger = _get_logger("llm_call")

    if error:
        logger.warning(f"[llm:{model}] error={error} duration={duration_ms:.0f}ms")
    else:
        logger.info(
            f"[llm:{model}] "
            f"msgs={messages_count} tools={tools_count} "
            f"has_tool_calls={has_tool_calls} duration={duration_ms:.0f}ms"
        )


# ══════════════════════════════════════════════════════════════════════════
# 审计日志（审批操作）
# ══════════════════════════════════════════════════════════════════════════

def log_approval_action(
    session_id: str,
    action: str,
    approval_data: dict,
    user_id: str = "unknown",
) -> None:
    """记录人工审批操作"""
    logger = _get_logger("approval")

    logger.info(
        f"[approval:{action}] session={session_id} user={user_id} "
        f"vouchers={approval_data.get('voucher_count', 0)}"
    )

    try:
        from agent import config as _cfg
        _cfg.log_session_event(
            session_id,
            "approval_action",
            {
                "action": action,
                "approval_data": approval_data,
                "user_id": user_id,
                "ts": datetime.now().isoformat(),
            },
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
# 初始化（导出到 graph_v2）
# ══════════════════════════════════════════════════════════════════════════

def setup_logging():
    """初始化日志系统"""
    _get_logger("node_transition")
    _get_logger("tool_call")
    _get_logger("llm_call")
    _get_logger("approval")
    print(f"[Logging] 日志目录: {LOG_DIR}")


def get_trace_path(session_id: str) -> Path:
    """获取指定 session 的 trace 日志文件路径"""
    return LOG_DIR / f"trace_{session_id}.jsonl"
