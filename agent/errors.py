# -*- coding: utf-8 -*-
"""
财务智能体 - 结构化错误类

定义统一的错误类型，包含错误码、用户友好消息和详细信息。
所有异常都继承自 FinanceAgentError，便于 FastAPI 全局捕获和前端分类展示。
"""

from __future__ import annotations

from typing import Optional, Dict, Any


class FinanceAgentError(Exception):
    """
    财务智能体基础异常类

    Attributes:
        code: 错误码（用于前端分类展示）
        message: 用户友好的错误消息
        details: 详细信息（调试用）
    """

    code: str = "UNKNOWN_ERROR"
    message: str = "未知错误"
    details: Optional[Dict[str, Any]] = None

    def __init__(
        self,
        message: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于 API 响应）"""
        return {
            "success": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# ══════════════════════════════════════════════════════════════════════════
# 配置相关错误
# ══════════════════════════════════════════════════════════════════════════

class ConfigError(FinanceAgentError):
    """配置错误"""
    code = "CONFIG_ERROR"
    message = "配置错误"


class MissingConfigError(ConfigError):
    """缺少必需配置"""
    code = "MISSING_CONFIG"
    message = "缺少必需的配置项"

    def __init__(self, config_name: str, env_var: str = None):
        details = {"config_name": config_name}
        if env_var:
            details["env_var"] = env_var
            details["hint"] = f"请在 .env 文件中设置 {env_var}"
        super().__init__(
            message=f"缺少必需配置：{config_name}",
            details=details,
        )


class InvalidConfigError(ConfigError):
    """配置值无效"""
    code = "INVALID_CONFIG"
    message = "配置值无效"

    def __init__(self, config_name: str, value: Any, reason: str = None):
        details = {"config_name": config_name, "value": str(value)}
        if reason:
            details["reason"] = reason
        super().__init__(
            message=f"配置 '{config_name}' 值无效：{reason or value}",
            details=details,
        )


# ══════════════════════════════════════════════════════════════════════════
# 文件相关错误
# ══════════════════════════════════════════════════════════════════════════

class FileError(FinanceAgentError):
    """文件操作错误"""
    code = "FILE_ERROR"
    message = "文件操作失败"


class FileNotFoundError(FileError):
    """文件不存在"""
    code = "FILE_NOT_FOUND"
    message = "文件不存在"

    def __init__(self, file_path: str):
        super().__init__(
            message=f"文件不存在：{file_path}",
            details={"file_path": file_path},
        )


class FileFormatError(FileError):
    """文件格式错误"""
    code = "FILE_FORMAT_ERROR"
    message = "文件格式不正确"

    def __init__(self, file_path: str, expected_format: str = None, actual_format: str = None):
        details = {"file_path": file_path}
        if expected_format:
            details["expected_format"] = expected_format
        if actual_format:
            details["actual_format"] = actual_format
        msg = f"文件格式不正确：{file_path}"
        if expected_format:
            msg += f"，期望格式：{expected_format}"
        super().__init__(message=msg, details=details)


class FileReadError(FileError):
    """文件读取失败"""
    code = "FILE_READ_ERROR"
    message = "文件读取失败"

    def __init__(self, file_path: str, reason: str = None):
        details = {"file_path": file_path}
        if reason:
            details["reason"] = reason
        super().__init__(
            message=f"无法读取文件：{file_path}，{reason or '未知原因'}",
            details=details,
        )


# ══════════════════════════════════════════════════════════════════════════
# Skill 相关错误
# ══════════════════════════════════════════════════════════════════════════

class SkillError(FinanceAgentError):
    """Skill 工具错误"""
    code = "SKILL_ERROR"
    message = "工具执行失败"


class SkillNotFoundError(SkillError):
    """Skill 不存在"""
    code = "SKILL_NOT_FOUND"
    message = "未找到指定的工具"

    def __init__(self, skill_name: str, available_skills: list = None):
        details = {"skill_name": skill_name}
        if available_skills:
            details["available_skills"] = available_skills
            details["hint"] = f"可用的工具：{', '.join(available_skills)}"
        super().__init__(
            message=f"未找到工具：{skill_name}",
            details=details,
        )


class ToolNotFoundError(SkillError):
    """工具函数不存在"""
    code = "TOOL_NOT_FOUND"
    message = "未找到工具函数"

    def __init__(self, tool_name: str, skill_name: str = None):
        details = {"tool_name": tool_name}
        if skill_name:
            details["skill_name"] = skill_name
        super().__init__(
            message=f"未找到工具函数：{tool_name}",
            details=details,
        )


class SkillExecutionError(SkillError):
    """Skill 执行失败"""
    code = "SKILL_EXECUTION_ERROR"
    message = "工具执行过程中发生错误"

    def __init__(self, tool_name: str, reason: str = None, traceback: str = None):
        details = {"tool_name": tool_name}
        if reason:
            details["reason"] = reason
        if traceback:
            details["traceback"] = traceback
        super().__init__(
            message=f"工具 '{tool_name}' 执行失败：{reason or '未知原因'}",
            details=details,
        )


class MissingParameterError(SkillError):
    """缺少必需参数"""
    code = "MISSING_PARAMETER"
    message = "缺少必需参数"

    def __init__(self, tool_name: str, param_name: str):
        super().__init__(
            message=f"工具 '{tool_name}' 缺少必需参数：{param_name}",
            details={"tool_name": tool_name, "param_name": param_name},
        )


# ══════════════════════════════════════════════════════════════════════════
# LLM 相关错误
# ══════════════════════════════════════════════════════════════════════════

class LLMError(FinanceAgentError):
    """LLM 调用错误"""
    code = "LLM_ERROR"
    message = "AI 模型调用失败"


class LLMConnectionError(LLMError):
    """LLM 连接失败"""
    code = "LLM_CONNECTION_ERROR"
    message = "无法连接到 AI 服务"

    def __init__(self, api_url: str = None, reason: str = None):
        details = {}
        if api_url:
            details["api_url"] = api_url
        if reason:
            details["reason"] = reason
        super().__init__(
            message=f"无法连接 AI 服务：{reason or '网络错误'}",
            details=details,
        )


class LLMResponseError(LLMError):
    """LLM 响应异常"""
    code = "LLM_RESPONSE_ERROR"
    message = "AI 服务返回异常响应"

    def __init__(self, reason: str = None, response: dict = None):
        details = {}
        if reason:
            details["reason"] = reason
        if response:
            details["response"] = response
        super().__init__(
            message=f"AI 服务响应异常：{reason or '未知'}",
            details=details,
        )


class LLMTimeoutError(LLMError):
    """LLM 调用超时"""
    code = "LLM_TIMEOUT_ERROR"
    message = "AI 服务响应超时"

    def __init__(self, timeout: int = None):
        details = {}
        if timeout:
            details["timeout_seconds"] = timeout
        super().__init__(
            message=f"AI 服务响应超时（{timeout or '未知'}秒）",
            details=details,
        )


class LLMRateLimitError(LLMError):
    """LLM 请求频率限制"""
    code = "LLM_RATE_LIMIT_ERROR"
    message = "AI 服务请求频率超限，请稍后再试"

    def __init__(self, retry_after: int = None):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(details=details)


# ══════════════════════════════════════════════════════════════════════════
# Session 相关错误
# ══════════════════════════════════════════════════════════════════════════

class SessionError(FinanceAgentError):
    """Session 错误"""
    code = "SESSION_ERROR"
    message = "会话操作失败"


class SessionNotFoundError(SessionError):
    """Session 不存在"""
    code = "SESSION_NOT_FOUND"
    message = "会话不存在或已过期"

    def __init__(self, session_id: str):
        super().__init__(
            message=f"会话不存在：{session_id}",
            details={"session_id": session_id},
        )


class SessionExpiredError(SessionError):
    """Session 已过期"""
    code = "SESSION_EXPIRED"
    message = "会话已过期，请重新开始"

    def __init__(self, session_id: str, expired_at: str = None):
        details = {"session_id": session_id}
        if expired_at:
            details["expired_at"] = expired_at
        super().__init__(details=details)


# ══════════════════════════════════════════════════════════════════════════
# 审批相关错误
# ══════════════════════════════════════════════════════════════════════════

class ApprovalError(FinanceAgentError):
    """审批流程错误"""
    code = "APPROVAL_ERROR"
    message = "审批操作失败"


class ApprovalNotFoundError(ApprovalError):
    """审批请求不存在"""
    code = "APPROVAL_NOT_FOUND"
    message = "没有待审批的请求"

    def __init__(self, session_id: str = None):
        details = {}
        if session_id:
            details["session_id"] = session_id
        super().__init__(details=details)


class ApprovalAlreadyProcessedError(ApprovalError):
    """审批已处理"""
    code = "APPROVAL_ALREADY_PROCESSED"
    message = "该审批请求已处理"

    def __init__(self, session_id: str, action: str = None):
        details = {"session_id": session_id}
        if action:
            details["previous_action"] = action
        super().__init__(details=details)


class ApprovalTimeoutError(ApprovalError):
    """审批超时"""
    code = "APPROVAL_TIMEOUT"
    message = "审批等待超时，已自动取消"

    def __init__(self, session_id: str, timeout_seconds: int = None):
        details = {"session_id": session_id}
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(details=details)


# ══════════════════════════════════════════════════════════════════════════
# RAG 相关错误
# ══════════════════════════════════════════════════════════════════════════

class RAGError(FinanceAgentError):
    """RAG 知识库错误"""
    code = "RAG_ERROR"
    message = "知识库操作失败"


class KnowledgeBaseNotFoundError(RAGError):
    """知识库不存在"""
    code = "KB_NOT_FOUND"
    message = "知识库未初始化"

    def __init__(self, knowledge_dir: str = None):
        details = {}
        if knowledge_dir:
            details["knowledge_dir"] = knowledge_dir
        super().__init__(details=details)


class EmbeddingError(RAGError):
    """Embedding 失败"""
    code = "EMBEDDING_ERROR"
    message = "文本向量化失败"

    def __init__(self, reason: str = None):
        details = {}
        if reason:
            details["reason"] = reason
        super().__init__(
            message=f"文本向量化失败：{reason or '未知原因'}",
            details=details,
        )


class VectorStoreError(RAGError):
    """向量存储错误"""
    code = "VECTOR_STORE_ERROR"
    message = "向量数据库操作失败"

    def __init__(self, operation: str = None, reason: str = None):
        details = {}
        if operation:
            details["operation"] = operation
        if reason:
            details["reason"] = reason
        super().__init__(
            message=f"向量数据库 {operation or '操作'}失败：{reason or '未知'}",
            details=details,
        )


# ══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════════════

def error_response(error: FinanceAgentError) -> Dict[str, Any]:
    """
    将异常转换为 API 响应格式

    Args:
        error: FinanceAgentError 实例

    Returns:
        dict，包含 success=false 和 error 详情
    """
    return error.to_dict()


def wrap_exception(exc: Exception, default_error_class: FinanceAgentError = None) -> FinanceAgentError:
    """
    将普通异常包装为 FinanceAgentError

    Args:
        exc: 原始异常
        default_error_class: 默认错误类型（未匹配时使用）

    Returns:
        FinanceAgentError 实例
    """
    if isinstance(exc, FinanceAgentError):
        return exc

    default_class = default_error_class or FinanceAgentError
    import traceback
    return default_class(
        message=str(exc),
        details={"traceback": traceback.format_exc(), "original_type": type(exc).__name__},
    )