# -*- coding: utf-8 -*-
"""
FastAPI 全局异常处理器

将所有异常转换为结构化的 JSON 响应，便于前端分类展示。
"""

from __future__ import annotations

import traceback
import sys
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from agent.errors import (
    FinanceAgentError,
    wrap_exception,
    error_response,
)


# ══════════════════════════════════════════════════════════════════════════
# 异常处理器
# ══════════════════════════════════════════════════════════════════════════

async def finance_agent_exception_handler(
    request: Request,
    exc: FinanceAgentError,
) -> JSONResponse:
    """
    处理 FinanceAgentError 及其子类

    返回结构化的错误响应：
    {
        "success": false,
        "error": {
            "code": "FILE_FORMAT_ERROR",
            "message": "文件格式不正确...",
            "details": {...}
        }
    }
    """
    # 记录错误日志
    sys.stderr.write(
        f"[ErrorHandler] {exc.code}: {exc.message}\n"
        f"  Path: {request.url.path}\n"
        f"  Details: {exc.details}\n"
    )
    sys.stderr.flush()

    return JSONResponse(
        status_code=_get_http_status(exc),
        content=error_response(exc),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    处理请求参数验证错误

    将 FastAPI 的验证错误转换为统一格式
    """
    errors = exc.errors()
    error_messages = []
    for err in errors:
        loc = " -> ".join(str(x) for x in err.get("loc", []))
        msg = err.get("msg", "验证失败")
        error_messages.append(f"{loc}: {msg}")

    sys.stderr.write(
        f"[ErrorHandler] VALIDATION_ERROR: {error_messages}\n"
        f"  Path: {request.url.path}\n"
    )
    sys.stderr.flush()

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数验证失败",
                "details": {
                    "errors": errors,
                    "messages": error_messages,
                },
            },
        },
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """
    处理 HTTP 异常（404、500 等）
    """
    sys.stderr.write(
        f"[ErrorHandler] HTTP_{exc.status_code}: {exc.detail}\n"
        f"  Path: {request.url.path}\n"
    )
    sys.stderr.flush()

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": str(exc.detail),
                "details": {"status_code": exc.status_code},
            },
        },
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    处理所有未捕获的异常

    包装为 FinanceAgentError 后返回
    """
    wrapped = wrap_exception(exc)
    tb = traceback.format_exc()

    sys.stderr.write(
        f"[ErrorHandler] UNHANDLED_EXCEPTION: {type(exc).__name__}\n"
        f"  Path: {request.url.path}\n"
        f"  Traceback:\n{tb}\n"
    )
    sys.stderr.flush()

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
                "details": {
                    "original_type": type(exc).__name__,
                    "original_message": str(exc),
                    "traceback": tb if "--debug" in sys.argv else None,
                },
            },
        },
    )


# ══════════════════════════════════════════════════════════════════════════
# HTTP 状态码映射
# ══════════════════════════════════════════════════════════════════════════

def _get_http_status(exc: FinanceAgentError) -> int:
    """
    根据错误类型返回合适的 HTTP 状态码
    """
    # 配置错误 → 500（服务端问题）
    if exc.code.startswith("CONFIG") or exc.code.startswith("MISSING"):
        return 500

    # 文件不存在 → 404
    if exc.code == "FILE_NOT_FOUND":
        return 404

    # 文件格式错误 → 400
    if exc.code in ("FILE_FORMAT_ERROR", "FILE_READ_ERROR"):
        return 400

    # Skill/Tool 不存在 → 404
    if exc.code in ("SKILL_NOT_FOUND", "TOOL_NOT_FOUND"):
        return 404

    # 参数缺失 → 400
    if exc.code == "MISSING_PARAMETER":
        return 400

    # Session 不存在 → 404
    if exc.code in ("SESSION_NOT_FOUND", "SESSION_EXPIRED"):
        return 404

    # 审批相关 → 400 或 404
    if exc.code in ("APPROVAL_NOT_FOUND", "APPROVAL_ALREADY_PROCESSED"):
        return 404
    if exc.code == "APPROVAL_TIMEOUT":
        return 408

    # LLM 错误 → 503（服务不可用）
    if exc.code.startswith("LLM"):
        if exc.code == "LLM_RATE_LIMIT_ERROR":
            return 429
        return 503

    # RAG 错误 → 500
    if exc.code.startswith("RAG") or exc.code.startswith("KB") or exc.code.startswith("EMBEDDING"):
        return 500

    # 默认 → 500
    return 500


# ══════════════════════════════════════════════════════════════════════════
# 注册函数
# ══════════════════════════════════════════════════════════════════════════

def register_exception_handlers(app) -> None:
    """
    在 FastAPI 应用中注册所有异常处理器

    Usage:
        from fastapi import FastAPI
        from agent.middleware.error_handler import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
    """
    # FinanceAgentError 及子类
    app.add_exception_handler(FinanceAgentError, finance_agent_exception_handler)

    # FastAPI 验证错误
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Starlette HTTP 异常
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # 所有其他异常
    app.add_exception_handler(Exception, generic_exception_handler)

    print("[ErrorHandler] 异常处理器已注册")