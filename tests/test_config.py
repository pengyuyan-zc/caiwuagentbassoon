# -*- coding: utf-8 -*-
"""
配置模块测试

测试 agent/config.py 的功能：
  - 配置加载
  - 配置验证
  - Session 管理
"""

import pytest

from agent.errors import MissingConfigError


class TestConfigLoad:
    """配置加载测试"""

    def test_dashscope_config_loaded(self, mock_env):
        """测试 DashScope 配置是否正确加载"""
        from agent import config

        assert config.dashscope.api_key == "sk-test-key-for-unit-tests"
        assert config.dashscope.api_url is not None
        assert config.dashscope.embedding_model == "text-embedding-v3"

    def test_agent_config_loaded(self, mock_env):
        """测试 Agent 配置是否正确加载"""
        from agent import config

        assert config.agent.model == "qwen-turbo"
        assert config.agent.max_loop == 5
        assert config.agent.max_react_turns == 20

    def test_server_config_loaded(self, mock_env):
        """测试 Server 配置是否正确加载"""
        from agent import config

        assert config.server.host == "127.0.0.1"
        assert config.server.port == 5001

    def test_rag_config_default(self, mock_env):
        """测试 RAG 配置默认值"""
        from agent import config

        assert config.rag.enabled is False
        assert config.rag.top_k == 5


class TestConfigValidation:
    """配置验证测试"""

    def test_validate_config_returns_results(self, mock_env):
        """测试 validate_config 返回验证结果"""
        from agent import config

        results = config.validate_config(strict=False)

        assert len(results) > 0
        assert all("name" in r for r in results)
        assert all("valid" in r for r in results)

    def test_validate_config_strict_raises_on_missing(self, clean_env):
        """测试严格模式下缺少配置会抛异常"""
        from agent import config as _config

        # 清空 API Key
        _config.dashscope.api_key = ""

        with pytest.raises(MissingConfigError) as exc_info:
            _config.validate_config(strict=True)

        assert exc_info.value.code == "MISSING_CONFIG"

    def test_check_startup_config_prints_status(self, mock_env, capsys):
        """测试启动配置检查输出"""
        from agent import config

        config.check_startup_config()

        captured = capsys.readouterr()
        assert "配置检查" in captured.out


class TestSessionManagement:
    """Session 管理测试"""

    def test_create_session(self, mock_env):
        """测试创建 Session"""
        from agent import config

        session_id = "test_session_001"
        result = config.create_session(session_id, "test_user")

        assert result["session_id"] == session_id
        assert result["user_id"] == "test_user"

    def test_get_session(self, mock_env):
        """测试获取 Session"""
        from agent import config

        session_id = "test_session_002"
        config.create_session(session_id, "test_user")

        result = config.get_session(session_id)

        assert result is not None
        assert result["session_id"] == session_id

    def test_get_nonexistent_session(self, mock_env):
        """测试获取不存在的 Session"""
        from agent import config

        result = config.get_session("nonexistent_session")

        assert result is None

    def test_delete_session(self, mock_env):
        """测试删除 Session"""
        from agent import config

        session_id = "test_session_003"
        config.create_session(session_id)

        deleted = config.delete_session(session_id)

        assert deleted is True
        assert config.get_session(session_id) is None

    def test_list_sessions(self, mock_env):
        """测试列出 Sessions"""
        from agent import config

        config.create_session("session_a")
        config.create_session("session_b")

        result = config.list_sessions()

        assert len(result) >= 2

    def test_log_session_event(self, mock_env):
        """测试记录 Session 事件"""
        from agent import config

        session_id = "test_session_004"
        config.create_session(session_id)

        config.log_session_event(session_id, "test_event", {"data": "test"})

        trace = config.get_session_trace(session_id)

        assert len(trace) > 0
        assert trace[-1]["event_type"] == "test_event"