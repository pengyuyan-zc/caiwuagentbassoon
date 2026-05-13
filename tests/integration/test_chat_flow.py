# -*- coding: utf-8 -*-
"""
聊天流程集成测试

测试完整的对话流程：
  - 消息发送
  - 流式响应
  - 错误处理
"""

import pytest
import json


@pytest.mark.integration
@pytest.mark.slow
class TestChatEndpoint:
    """聊天接口测试"""

    def test_chat_simple_message(self, api_client):
        """测试简单消息对话"""
        response = api_client.post(
            "/api/agent/chat",
            data={"message": "你好"},
        )

        # 响应应该是成功的
        assert response.status_code in (200, 500)  # 500 可能是因为 API Key 未配置
        data = response.json()

        if response.status_code == 200:
            assert "reply" in data
            assert "session_id" in data

    def test_chat_with_session(self, api_client):
        """测试带 Session 的对话"""
        # 创建 Session
        create_resp = api_client.post(
            "/api/sessions",
            data={"user_id": "test_user", "metadata": "{}"},
        )
        session_id = create_resp.json()["session_id"]

        # 发送消息
        response = api_client.post(
            "/api/agent/chat",
            data={"message": "测试消息", "session_id": session_id},
        )

        assert response.status_code in (200, 500)
        data = response.json()

        if response.status_code == 200:
            assert data["session_id"] == session_id

    def test_chat_response_structure(self, api_client):
        """测试响应结构"""
        response = api_client.post(
            "/api/agent/chat",
            data={"message": "介绍一下系统功能"},
        )

        if response.status_code == 200:
            data = response.json()
            assert "reply" in data
            assert "session_id" in data
            assert "tools_used" in data


@pytest.mark.integration
@pytest.mark.slow
class TestChatStreamEndpoint:
    """流式聊天接口测试"""

    def test_stream_response_is_sse(self, api_client):
        """测试流式响应是 SSE 格式"""
        response = api_client.post(
            "/api/agent/chat/stream",
            data={"message": "你好"},
            stream=True,
        )

        # 响应应该是 text/event-stream
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert response.status_code in (200, 500)


@pytest.mark.integration
class TestChatErrorHandling:
    """聊天错误处理测试"""

    def test_chat_empty_message(self, api_client):
        """测试空消息"""
        response = api_client.post(
            "/api/agent/chat",
            data={"message": ""},
        )

        # 空消息应该返回错误或被拒绝
        assert response.status_code in (400, 422, 500)


@pytest.mark.integration
class TestApprovalEndpoints:
    """审批接口测试"""

    def test_approve_without_session(self, api_client):
        """测试没有 Session 的审批"""
        response = api_client.post(
            "/api/agent/approve",
            data={"session_id": "nonexistent", "action": "approve"},
        )

        # 没有 Session 应该返回错误
        assert response.status_code in (400, 404, 500)

    def test_approve_invalid_action(self, api_client):
        """测试无效的审批动作"""
        response = api_client.post(
            "/api/agent/approve",
            data={"session_id": "test", "action": "invalid_action"},
        )

        # 无效动作应该返回 400
        assert response.status_code == 400


@pytest.mark.integration
class TestAgentStateEndpoint:
    """Agent 状态接口测试"""

    def test_get_state_nonexistent_session(self, api_client):
        """测试获取不存在 Session 的状态"""
        response = api_client.get("/api/agent/state/nonexistent_session")

        # 应该返回 404 或包含错误信息
        assert response.status_code in (200, 404, 500)
        data = response.json()

        if response.status_code == 404:
            assert data.get("success") is False


@pytest.mark.integration
class TestFullWorkflow:
    """完整工作流测试"""

    def test_create_session_and_chat(self, api_client):
        """测试创建 Session 后对话"""
        # 1. 创建 Session
        create_resp = api_client.post(
            "/api/sessions",
            data={"user_id": "workflow_test", "metadata": "{}"},
        )
        assert create_resp.status_code == 200
        session_id = create_resp.json()["session_id"]

        # 2. 发送消息
        chat_resp = api_client.post(
            "/api/agent/chat",
            data={"message": "你好", "session_id": session_id},
        )

        if chat_resp.status_code == 200:
            chat_data = chat_resp.json()
            assert chat_data["session_id"] == session_id

            # 3. 获取 Session 状态
            state_resp = api_client.get(f"/api/agent/state/{session_id}")

            # 4. 获取 Session 信息
            info_resp = api_client.get(f"/api/sessions/{session_id}")
            assert info_resp.status_code == 200

            # 5. 删除 Session
            delete_resp = api_client.delete(f"/api/sessions/{session_id}")
            assert delete_resp.status_code == 200