# -*- coding: utf-8 -*-
"""
Helpers 模块测试

测试 agent/helpers.py 的功能：
  - Skill 加载
  - Skill 列表
  - 系统提示词构建
"""

import pytest


class TestSkillLoading:
    """Skill 加载测试"""

    def test_list_skills_returns_list(self, mock_env):
        """测试 list_skills 返回列表"""
        from agent.helpers import list_skills

        skills = list_skills()

        assert isinstance(skills, list)
        assert len(skills) > 0

    def test_skill_has_required_fields(self, mock_env):
        """测试 Skill 包含必需字段"""
        from agent.helpers import list_skills

        skills = list_skills()

        for skill in skills:
            assert "name" in skill
            assert "path" in skill
            assert isinstance(skill["name"], str)

    def test_skill_directory_exists(self, mock_env):
        """测试 Skill 目录存在"""
        from agent.helpers import list_skills, _SKILLS_DIR

        assert _SKILLS_DIR.exists()
        skills = list_skills()
        for skill in skills:
            path = skill["path"]
            # 路径应该存在或至少格式正确
            assert path is not None


class TestSkillDescription:
    """Skill 描述读取测试"""

    def test_read_skill_description(self, mock_env):
        """测试读取 Skill 描述"""
        from agent.helpers import _read_skill_description
        from pathlib import Path

        # 测试一个已存在的 SKILL.md
        skills_dir = Path(__file__).parent.parent / "agent" / "skills"
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    desc = _read_skill_description(skill_md)
                    assert isinstance(desc, str)
                    break


class TestSystemPrompt:
    """系统提示词构建测试"""

    def test_build_skill_system_prompt(self, mock_env):
        """测试构建系统提示词"""
        from agent.helpers import _build_skill_system_prompt

        prompt = _build_skill_system_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "财务助手" in prompt or "Skills" in prompt

    def test_system_prompt_contains_skill_names(self, mock_env):
        """测试系统提示词包含 Skill 名称"""
        from agent.helpers import _build_skill_system_prompt, list_skills

        prompt = _build_skill_system_prompt()
        skills = list_skills()

        for skill in skills:
            # 提示词中应包含 Skill 名称或其工具函数
            assert skill["name"] in prompt or any(kw in prompt for kw in ["invoice", "salary", "voucher"])


class TestToolsLoading:
    """工具加载测试"""

    def test_load_tools_from_skills(self, mock_env):
        """测试从 Skills 加载工具"""
        from agent.helpers import _load_tools_from_skills

        tools = _load_tools_from_skills()

        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_tools_have_correct_format(self, mock_env):
        """测试工具格式正确"""
        from agent.helpers import _load_tools_from_skills

        tools = _load_tools_from_skills()

        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]


class TestInvokeSkill:
    """Skill 调用测试"""

    def test_invoke_skill_returns_dict(self, mock_env):
        """测试 invoke_skill 返回字典"""
        from agent.helpers import invoke_skill

        # 测试调用不存在的 Skill
        result = invoke_skill("nonexistent_skill")

        assert isinstance(result, dict)
        assert result.get("success") is False

    def test_invoke_skill_error_message(self, mock_env):
        """测试 invoke_skill 错误消息"""
        from agent.helpers import invoke_skill

        result = invoke_skill("nonexistent_skill")

        assert "message" in result
        assert "未找到" in result["message"] or "error" in result


class TestDashScopeCall:
    """DashScope API 调用测试"""

    @pytest.mark.integration
    def test_call_dashscope_with_mock(self, mock_env, mock_dashscope_response):
        """测试 DashScope API 调用（需要 Mock 或真实 API）"""
        # 此测试标记为 integration，实际运行需要网络或 Mock
        # 在单元测试中跳过
        pass


class TestConfigFromConfigModule:
    """配置从 config.py 导入测试"""

    def test_api_key_from_config(self, mock_env):
        """测试 API Key 从 config 模块读取"""
        from agent.helpers import DASHSCOPE_API_KEY
        from agent import config

        assert DASHSCOPE_API_KEY == config.dashscope.api_key

    def test_api_url_from_config(self, mock_env):
        """测试 API URL 从 config 模块读取"""
        from agent.helpers import DASHSCOPE_API_URL
        from agent import config

        assert DASHSCOPE_API_URL == config.dashscope.api_url

    def test_model_from_config(self, mock_env):
        """测试模型名称从 config 模块读取"""
        from agent.helpers import DEFAULT_MODEL
        from agent import config

        assert DEFAULT_MODEL == config.agent.model

    def test_max_loop_from_config(self, mock_env):
        """测试最大循环次数从 config 模块读取"""
        from agent.helpers import MAX_LOOP
        from agent import config

        assert MAX_LOOP == config.agent.max_loop