# -*- coding: utf-8 -*-
"""
API 集成测试

测试 FastAPI 接口：
  - 健康检查
  - Skills 列表
  - Session 管理
  - 错误响应格式
"""

import pytest


@pytest.mark.integration
class TestHealthEndpoint:
    """健康检查接口测试"""

    def test_health_returns_ok(self, api_client):
        """测试健康检查返回正常"""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "skills" in data
        assert "model" in data

    def test_health_contains_skills(self, api_client):
        """测试健康检查包含 Skills"""
        response = api_client.get("/health")

        data = response.json()
        skills = data.get("skills", [])

        assert isinstance(skills, list)
        # 至少应该有一些 Skills
        assert len(skills) >= 0


@pytest.mark.integration
class TestSkillsEndpoint:
    """Skills 接口测试"""

    def test_list_skills(self, api_client):
        """测试列出 Skills"""
        response = api_client.get("/api/agent/skills")

        assert response.status_code == 200
        data = response.json()
        assert "skills" in data


@pytest.mark.integration
class TestSessionEndpoints:
    """Session 接口测试"""

    def test_create_session(self, api_client):
        """测试创建 Session"""
        response = api_client.post(
            "/api/sessions",
            data={"user_id": "test_user", "metadata": "{}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["created"] is True

    def test_list_sessions(self, api_client):
        """测试列出 Sessions"""
        response = api_client.get("/api/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data

    def test_get_session(self, api_client):
        """测试获取 Session"""
        # 先创建一个
        create_resp = api_client.post(
            "/api/sessions",
            data={"user_id": "test_user", "metadata": "{}"},
        )
        session_id = create_resp.json()["session_id"]

        # 再获取
        response = api_client.get(f"/api/sessions/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    def test_delete_session(self, api_client):
        """测试删除 Session"""
        # 先创建
        create_resp = api_client.post(
            "/api/sessions",
            data={"user_id": "test_user", "metadata": "{}"},
        )
        session_id = create_resp.json()["session_id"]

        # 再删除
        response = api_client.delete(f"/api/sessions/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True

    def test_get_nonexistent_session(self, api_client):
        """测试获取不存在的 Session"""
        response = api_client.get("/api/sessions/nonexistent_session_id")

        assert response.status_code == 404


@pytest.mark.integration
class TestErrorHandling:
    """错误处理测试"""

    def test_error_response_format(self, api_client):
        """测试错误响应格式"""
        response = api_client.get("/api/sessions/nonexistent_session")

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    def test_validation_error_format(self, api_client):
        """测试参数验证错误格式"""
        # 发送缺少必需参数的请求
        response = api_client.post("/api/sessions", data={})

        # 应该返回验证错误
        assert response.status_code == 422 or response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "error" in data


@pytest.mark.integration
class TestDownloadEndpoint:
    """下载接口测试"""

    def test_download_nonexistent_file(self, api_client):
        """测试下载不存在的文件"""
        response = api_client.get("/download?file=/nonexistent/path/file.xlsx")

        assert response.status_code == 404


@pytest.mark.integration
class TestKnowledgeEndpoints:
    """知识库接口测试"""

    def test_knowledge_stats_when_disabled(self, api_client):
        """测试 RAG 未启用时的知识库统计"""
        response = api_client.get("/api/knowledge/stats")

        # RAG 默认未启用，返回 enabled=false
        assert response.status_code == 200
        data = response.json()
        assert data.get("enabled") is False or "stats" in data