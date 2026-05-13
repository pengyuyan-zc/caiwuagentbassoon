# -*- coding: utf-8 -*-
"""
错误模块测试

测试 agent/errors.py 的功能：
  - 错误类创建
  - 错误响应格式
  - 错误码映射
"""

import pytest


class TestFinanceAgentError:
    """基础错误类测试"""

    def test_error_creation(self):
        """测试错误创建"""
        from agent.errors import FinanceAgentError

        error = FinanceAgentError(
            message="测试错误消息",
            code="TEST_ERROR",
            details={"key": "value"},
        )

        assert error.message == "测试错误消息"
        assert error.code == "TEST_ERROR"
        assert error.details == {"key": "value"}

    def test_error_to_dict(self):
        """测试错误转换为字典"""
        from agent.errors import FinanceAgentError

        error = FinanceAgentError(message="测试", code="TEST")
        result = error.to_dict()

        assert result["success"] is False
        assert "error" in result
        assert result["error"]["code"] == "TEST"
        assert result["error"]["message"] == "测试"

    def test_error_default_values(self):
        """测试错误默认值"""
        from agent.errors import FinanceAgentError

        error = FinanceAgentError()

        assert error.code == "UNKNOWN_ERROR"
        assert error.message == "未知错误"
        assert error.details == {}


class TestConfigErrors:
    """配置错误测试"""

    def test_missing_config_error(self):
        """测试缺少配置错误"""
        from agent.errors import MissingConfigError

        error = MissingConfigError("DASHSCOPE_API_KEY", "DASHSCOPE_API_KEY")

        assert error.code == "MISSING_CONFIG"
        assert "DASHSCOPE_API_KEY" in error.message
        assert "env_var" in error.details

    def test_invalid_config_error(self):
        """测试无效配置错误"""
        from agent.errors import InvalidConfigError

        error = InvalidConfigError("MAX_LOOP", "abc", "必须是数字")

        assert error.code == "INVALID_CONFIG"
        assert "MAX_LOOP" in error.message


class TestFileErrors:
    """文件错误测试"""

    def test_file_not_found_error(self):
        """测试文件不存在错误"""
        from agent.errors import FileNotFoundError

        error = FileNotFoundError("/path/to/file.xlsx")

        assert error.code == "FILE_NOT_FOUND"
        assert "/path/to/file.xlsx" in error.message

    def test_file_format_error(self):
        """测试文件格式错误"""
        from agent.errors import FileFormatError

        error = FileFormatError(
            "test.xlsx",
            expected_format="Excel (.xlsx)",
            actual_format="HTML",
        )

        assert error.code == "FILE_FORMAT_ERROR"
        assert "Excel" in error.message or "xlsx" in error.message


class TestSkillErrors:
    """Skill 错误测试"""

    def test_skill_not_found_error(self):
        """测试 Skill 不存在错误"""
        from agent.errors import SkillNotFoundError

        error = SkillNotFoundError(
            "unknown_skill",
            available_skills=["invoice-voucher", "salary-voucher"],
        )

        assert error.code == "SKILL_NOT_FOUND"
        assert "available_skills" in error.details

    def test_missing_parameter_error(self):
        """测试缺少参数错误"""
        from agent.errors import MissingParameterError

        error = MissingParameterError("invoke_invoice_voucher", "input_files")

        assert error.code == "MISSING_PARAMETER"
        assert "input_files" in error.message

    def test_skill_execution_error(self):
        """测试 Skill 执行错误"""
        from agent.errors import SkillExecutionError

        error = SkillExecutionError(
            "invoke_invoice_voucher",
            reason="文件解析失败",
            traceback="...",
        )

        assert error.code == "SKILL_EXECUTION_ERROR"
        assert "文件解析失败" in error.message


class TestLLMErrors:
    """LLM 错误测试"""

    def test_llm_connection_error(self):
        """测试 LLM 连接错误"""
        from agent.errors import LLMConnectionError

        error = LLMConnectionError(
            api_url="https://dashscope.aliyuncs.com",
            reason="网络超时",
        )

        assert error.code == "LLM_CONNECTION_ERROR"

    def test_llm_timeout_error(self):
        """测试 LLM 超时错误"""
        from agent.errors import LLMTimeoutError

        error = LLMTimeoutError(timeout=120)

        assert error.code == "LLM_TIMEOUT_ERROR"
        assert 120 in error.details.get("timeout_seconds", 0)

    def test_llm_rate_limit_error(self):
        """测试 LLM 频率限制错误"""
        from agent.errors import LLMRateLimitError

        error = LLMRateLimitError(retry_after=60)

        assert error.code == "LLM_RATE_LIMIT_ERROR"


class TestSessionErrors:
    """Session 错误测试"""

    def test_session_not_found_error(self):
        """测试 Session 不存在错误"""
        from agent.errors import SessionNotFoundError

        error = SessionNotFoundError("session_123")

        assert error.code == "SESSION_NOT_FOUND"
        assert "session_123" in error.message


class TestRAGErrors:
    """RAG 错误测试"""

    def test_embedding_error(self):
        """测试 Embedding 错误"""
        from agent.errors import EmbeddingError

        error = EmbeddingError(reason="API 返回空响应")

        assert error.code == "EMBEDDING_ERROR"

    def test_vector_store_error(self):
        """测试向量存储错误"""
        from agent.errors import VectorStoreError

        error = VectorStoreError(operation="search", reason="索引损坏")

        assert error.code == "VECTOR_STORE_ERROR"


class TestErrorResponse:
    """错误响应函数测试"""

    def test_error_response_function(self):
        """测试 error_response 函数"""
        from agent.errors import error_response, FinanceAgentError

        error = FinanceAgentError("测试", "TEST")
        result = error_response(error)

        assert result["success"] is False
        assert result["error"]["code"] == "TEST"

    def test_wrap_exception(self):
        """测试 wrap_exception 函数"""
        from agent.errors import wrap_exception

        # 包装普通异常
        exc = ValueError("测试值错误")
        wrapped = wrap_exception(exc)

        assert wrapped.code == "UNKNOWN_ERROR"
        assert "测试值错误" in wrapped.message
        assert "original_type" in wrapped.details

    def test_wrap_exception_preserves_finance_error(self):
        """测试 wrap_exception 保留 FinanceAgentError"""
        from agent.errors import wrap_exception, FileNotFoundError

        original = FileNotFoundError("/test/path")
        wrapped = wrap_exception(original)

        assert wrapped.code == "FILE_NOT_FOUND"
        assert wrapped.message == original.message