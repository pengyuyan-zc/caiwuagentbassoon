# Skill 开发指南

本文档说明如何为财务智能体开发新的 Skill 工具。

## Skill 目录结构

每个 Skill 应放在 `agent/skills/{skill-name}/` 目录下：

```
skills/
└── my-skill/                # Skill 名称（使用小写字母和连字符）
    ├── SKILL.md             # 技能描述（LLM 据此理解何时调用）
    ├── agent.py             # 执行逻辑 + TOOLS 定义（必须）
    ├── helper.py            # 辅助函数（可选）
    ├── templates/           # 模板文件（可选）
    │   └── template.xlsx
    └── data/                # 数据文件（可选）
        └── mapping.xlsx
```

---

## SKILL.md 格式

SKILL.md 是 Markdown 文件，包含 YAML frontmatter：

```markdown
---
name: my-skill
description: 简短描述，用于触发词匹配
---

# 我的新技能

当用户请求 XXX 时，立即使用此 skill。

## 功能说明

详细说明此 Skill 的功能...

## 触发词

- 生成XXX凭证
- X月XXX凭证
- XXX税务凭证

## 输入要求

说明需要的输入文件格式...
```

### 重要字段

| 字段 | 说明 |
|------|------|
| `name` | Skill 名称（必须与目录名一致） |
| `description` | 简短描述，用于 Skill 列表展示 |

---

## agent.py 格式

agent.py 必须包含：

1. **工具函数**：实际执行逻辑
2. **TOOLS 元数据**：供 LLM 调用的工具定义

### 基本结构

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Skill 名称 - 执行入口

工具列表：
  - invoke_my_skill: 执行 XXX
"""

from pathlib import Path
import json
from typing import Any

# Skill 目录和项目根目录
_SKILL_DIR = Path(__file__).parent
_PROJECT_ROOT = _SKILL_DIR.parent.parent

# 导入错误类
from agent.errors import (
    FileNotFoundError,
    FileFormatError,
    SkillExecutionError,
    MissingParameterError,
    error_response,
)

# ─────────────────────────────────────────────────────────────────────
# 业务函数（内部实现）
# ─────────────────────────────────────────────────────────────────────

def _run_my_skill(input_file: str, output_dir: str = None) -> dict[str, Any]:
    """内部实现逻辑"""
    input_path = Path(input_file)
    
    # 检查文件存在
    if not input_path.exists():
        return error_response(FileNotFoundError(input_file))
    
    # 检查文件格式
    header = input_path.read_bytes()[:8]
    if not header.startswith(b"PK"):  # Excel 文件检查
        return error_response(FileFormatError(
            input_file,
            expected_format="Excel (.xlsx)",
            actual_format="非Excel文件",
        ))
    
    # 执行业务逻辑
    try:
        # ... 处理逻辑 ...
        return {
            "success": True,
            "output_file": str(output_path),
            "count": 10,
            "message": "处理完成！",
        }
    except Exception as e:
        import traceback
        return error_response(SkillExecutionError(
            "invoke_my_skill",
            reason=str(e),
            traceback=traceback.format_exc(),
        ))


# ─────────────────────────────────────────────────────────────────────
# 工具函数（供 LLM 调用）
# ─────────────────────────────────────────────────────────────────────

def invoke_my_skill(input_file: str, output_dir: str = None) -> str:
    """
    执行 XXX 功能。

    参数：
        input_file: 输入文件路径（.xlsx 或 .xls），必须提供。
        output_dir: 输出目录，默认为输入文件所在目录。

    返回：
        JSON 字符串，包含执行结果。
    """
    # 参数检查
    if not input_file:
        return json.dumps(error_response(MissingParameterError(
            "invoke_my_skill",
            "input_file",
        )), ensure_ascii=False)
    
    # 调用内部实现
    try:
        result = _run_my_skill(input_file, output_dir)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps(error_response(SkillExecutionError(
            "invoke_my_skill",
            reason=str(e),
            traceback=traceback.format_exc(),
        )), ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────
# 工具元数据（LLM 据此调用）
# ─────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "invoke_my_skill",
            "description": (
                "执行 XXX 功能。"
                "根据用户上传的 Excel 文件自动生成 XXX。"
                "触发词：生成XXX、X月XXX、XXX凭证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_file": {
                        "type": "string",
                        "description": "输入 Excel 文件的完整路径（.xlsx 或 .xls），必填。"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "输出目录，默认为输入文件所在目录"
                    }
                },
                "required": ["input_file"]
            }
        }
    }
]
```

---

## TOOLS 定义规范

### 必需字段

| 字段 | 说明 |
|------|------|
| `type` | 固定为 `"function"` |
| `function.name` | 工具函数名（必须与 agent.py 中函数名一致） |
| `function.description` | 工具描述（包含触发词） |
| `function.parameters` | 参数定义（JSON Schema 格式） |

### 参数定义示例

```python
"parameters": {
    "type": "object",
    "properties": {
        "input_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "文件路径列表"
        },
        "month": {
            "type": "string",
            "description": "月份，如 '2024-01'"
        },
        "options": {
            "type": "object",
            "properties": {
                "verbose": {"type": "boolean"},
                "mode": {"type": "string", "enum": ["fast", "full"]}
            }
        }
    },
    "required": ["input_files"]
}
```

---

## 错误处理规范

### 使用结构化错误

所有 Skill 应使用 `agent.errors` 中的错误类：

```python
from agent.errors import (
    FileNotFoundError,      # 文件不存在
    FileFormatError,        # 文件格式错误
    MissingParameterError,  # 缺少参数
    SkillExecutionError,    # 执行错误
    error_response,         # 转换为响应格式
)
```

### 错误返回格式

```python
# 正确的错误返回方式
return error_response(FileNotFoundError(file_path))
# 输出: {"success": false, "error": {"code": "FILE_NOT_FOUND", "message": "...", "details": {...}}}

# 错误的方式（已废弃）
return {"success": False, "message": "文件不存在"}  # ❌ 不要这样写
```

---

## 返回值规范

### 成功响应

```python
return {
    "success": True,
    "output_file": str(output_path),  # 生成的文件路径
    "voucher_count": 15,              # 凭证数量（可选）
    "line_count": 45,                 # 分录数量（可选）
    "message": "生成完成！",
}
```

### 响应字段命名

| 场景 | 推荐字段 |
|------|---------|
| 凭证类 | `voucher_count`, `line_count` |
| 审批类 | `approval_count`, `entry_count` |
| 错误数 | `error_count` |

---

## 测试 Skill

### 单元测试

在 `tests/test_skills/` 下创建测试文件：

```python
# tests/test_skills/test_my_skill.py

import pytest
from pathlib import Path

class TestMySkill:
    def test_invoke_with_valid_file(self, sample_excel_file):
        """测试正常文件"""
        from agent.skills.my_skill.agent import invoke_my_skill
        
        result = invoke_my_skill(str(sample_excel_file))
        data = json.loads(result)
        
        assert data["success"] is True
    
    def test_invoke_with_missing_file(self):
        """测试文件不存在"""
        from agent.skills.my_skill.agent import invoke_my_skill
        
        result = invoke_my_skill("/nonexistent/file.xlsx")
        data = json.loads(result)
        
        assert data["success"] is False
        assert data["error"]["code"] == "FILE_NOT_FOUND"
```

---

## 最佳实践

1. **文件检查**：始终检查文件存在性和格式
2. **参数验证**：检查必需参数是否提供
3. **错误处理**：使用结构化错误，便于前端展示
4. **描述清晰**：TOOLS 中的 description 应包含触发词
5. **返回路径**：成功时返回 `output_file` 便于下载
6. **幂等性**：相同输入应产生相同输出（或可预测的差异）