# -*- coding: utf-8 -*-
"""
pytest 配置和 fixtures

提供测试所需的共享 fixtures：
  - mock_env: 模拟环境变量
  - mock_dashscope_api: Mock DashScope API 调用
  - temp_upload_dir: 临时上传目录
  - sample_excel_file: 示例 Excel 文件
"""

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest


# ══════════════════════════════════════════════════════════════════════════
# 环境变量 Mock
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def mock_env():
    """
    设置测试环境变量（会话级别）
    """
    original_env = os.environ.copy()

    # 设置测试所需的必需配置
    os.environ.setdefault("DASHSCOPE_API_KEY", "sk-test-key-for-unit-tests")
    os.environ.setdefault("LLM_MODEL", "qwen-turbo")
    os.environ.setdefault("MAX_LOOP", "5")
    os.environ.setdefault("RAG_ENABLED", "false")
    os.environ.setdefault("HUMAN_APPROVAL_ENABLED", "false")
    os.environ.setdefault("API_HOST", "127.0.0.1")
    os.environ.setdefault("API_PORT", "5001")

    yield

    # 恢复原始环境变量
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def clean_env():
    """
    每个测试前重置环境变量（函数级别）
    """
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


# ══════════════════════════════════════════════════════════════════════════
# 临时目录
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_upload_dir() -> Generator[Path, None, None]:
    """
    创建临时上传目录（测试结束后自动清理）
    """
    with tempfile.TemporaryDirectory(prefix="test_upload_") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_output_dir() -> Generator[Path, None, None]:
    """
    创建临时输出目录（测试结束后自动清理）
    """
    with tempfile.TemporaryDirectory(prefix="test_output_") as tmpdir:
        yield Path(tmpdir)


# ══════════════════════════════════════════════════════════════════════════
# Mock DashScope API
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_dashscope_response():
    """
    Mock DashScope API 响应数据
    """
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "这是一个测试回复。",
                }
            }
        ]
    }


@pytest.fixture
def mock_dashscope_tool_call_response():
    """
    Mock DashScope API 工具调用响应
    """
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_001",
                            "function": {
                                "name": "invoke_invoice_voucher",
                                "arguments": '{"input_files": ["test.xlsx"]}'
                            }
                        }
                    ]
                }
            }
        ]
    }


# ══════════════════════════════════════════════════════════════════════════
# 示例文件
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_excel_file(temp_upload_dir: Path) -> Path:
    """
    创建一个示例 Excel 文件（仅用于测试文件存在性）
    注意：这不是真实的金蝶云格式文件，仅用于路径测试
    """
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    # 添加一些测试数据
    ws.append(["审批编号", "客户名称", "开票总额", "不含税金额", "税额"])
    ws.append(["001", "测试客户A", "10000", "9000", "1000"])
    ws.append(["002", "测试客户B", "20000", "18000", "2000"])

    file_path = temp_upload_dir / "test_sample.xlsx"
    wb.save(str(file_path))
    return file_path


@pytest.fixture
def invalid_file(temp_upload_dir: Path) -> Path:
    """
    创建一个非 Excel 格式的文件（用于测试错误处理）
    """
    file_path = temp_upload_dir / "invalid_file.txt"
    file_path.write_text("This is not an Excel file")
    return file_path


# ══════════════════════════════════════════════════════════════════════════
# FastAPI Test Client
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def api_client():
    """
    创建 FastAPI Test Client（用于集成测试）
    """
    from fastapi.testclient import TestClient
    # 延迟导入避免循环依赖
    from agent.server import app
    return TestClient(app)