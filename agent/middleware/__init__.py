# -*- coding: utf-8 -*-
"""
中间件包

包含：
  - logging.py: 结构化日志中间件
  - error_handler.py: FastAPI 全局异常处理器
"""

from agent.middleware.logging import (
    setup_logging,
    log_node_transition,
    log_tool_call,
    log_llm_call,
    log_approval_action,
    get_trace_path,
)

from agent.middleware.error_handler import (
    register_exception_handlers,
    finance_agent_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    generic_exception_handler,
)

__all__ = [
    "setup_logging",
    "log_node_transition",
    "log_tool_call",
    "log_llm_call",
    "log_approval_action",
    "get_trace_path",
    "register_exception_handlers",
    "finance_agent_exception_handler",
    "validation_exception_handler",
    "http_exception_handler",
    "generic_exception_handler",
]
