# -*- coding: utf-8 -*-
from __future__ import annotations

"""
工资报酬税务凭证生成 - Skill 执行入口（deep-agent 工具）

供 deep-agent 的 LLM 通过工具调用此 skill。

工具列表：
  - invoke_salary_tax_voucher: 生成工资报酬税务凭证
"""

import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_SKILL_DIR = Path(__file__).parent
_PROJECT_ROOT = _SKILL_DIR.parent.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

# ── 导入结构化错误类 ──────────────────────────────────────────────────────
from agent.errors import (
    FileNotFoundError,
    FileFormatError,
    SkillExecutionError,
    MissingParameterError,
    error_response,
)


# ─────────────────────────────────────────────────────────────────────
# 业务函数（实际执行逻辑）
# ─────────────────────────────────────────────────────────────────────

def _run_salary_tax_voucher(
    input_file: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    生成工资报酬税务凭证的内部实现。

    Args:
        input_file: 工资报酬支付申请审批表 Excel 文件路径
        output_dir:  输出目录，默认同输入文件

    Returns:
        dict，包含 success / output_file / approval_count / entry_count / error_count / message
    """
    import re as _re

    input_path = Path(input_file)
    if not input_path.exists():
        return error_response(FileNotFoundError(str(input_path)))

    out_dir = Path(output_dir) if output_dir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # 凭证模板：在 skill 目录或桌面搜索
    template_path = _find_file("凭证表.xlsx", ["*.xlsx"])
    if not template_path:
        return {"success": False, "message": "凭证模板（凭证表.xlsx）未找到，请放在 skill 目录或桌面"}

    # 账簿映射
    account_book_path = _find_file("公司主体账套号.xlsx", ["*.xlsx"])

    # 客户映射
    customer_path = _find_file("客户账套.xlsx", ["*.xlsx"])

    # 银行日记账
    bank_journal_path = _find_file("银行存款日记账.xlsx", ["*.xlsx"])

    script_path = _SKILL_DIR / "salary_voucher_generator.py"
    if not script_path.exists():
        return {"success": False, "message": f"执行脚本不存在：{script_path}"}

    args = [
        sys.executable,
        str(script_path),
    ]
    # 不传参数，脚本内部会用硬编码的默认文件名（审批表.xlsx 等）
    # 为了支持用户指定输入文件，改用 subprocess + 参数方式
    # 但脚本 main() 是固定文件名，所以改用直接调用函数
    return _run_via_import(
        input_file=input_path,
        output_dir=out_dir,
        template_path=template_path,
        account_book_path=account_book_path,
        customer_path=customer_path,
        bank_journal_path=bank_journal_path,
    )


def _find_file(name: str, _patterns: list[str]) -> Path | None:
    """在 skill 目录和桌面搜索指定文件。"""
    candidates = [_SKILL_DIR / name]
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        candidates.append(desktop / name)
    for p in candidates:
        if p.exists():
            return p
    return None


def _run_via_import(
    input_file: Path,
    output_dir: Path,
    template_path: Path,
    account_book_path: Path | None,
    customer_path: Path | None,
    bank_journal_path: Path | None,
) -> dict[str, Any]:
    """通过 import 方式调用脚本函数。"""
    from salary_voucher_generator import generate_salary_voucher_files

    try:
        result = generate_salary_voucher_files(
            approval_path=input_file,
            template_path=template_path,
            output_dir=output_dir,
            account_book_mapping_path=account_book_path,
            customer_mapping_path=customer_path,
        )
        out_file = output_dir / "工资报酬凭证.xlsx"
        return {
            "success": True,
            "output_file": str(out_file),
            "approval_count": result.get("approval_count", 0),
            "entry_count": result.get("entry_count", 0),
            "error_count": result.get("error_count", 0),
            "message": f"生成完成！共 {result.get('approval_count', 0)} 张凭证，{result.get('entry_count', 0)} 条分录，{result.get('error_count', 0)} 条错误",
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "message": f"执行失败: {e}\n{traceback.format_exc()}"
        }


# ─────────────────────────────────────────────────────────────────────
# Deep-agent 工具定义（供 LLM 调用）
# ─────────────────────────────────────────────────────────────────────

def invoke_salary_tax_voucher(
    input_file: str,
    output_dir: str | None = None,
) -> str:
    """
    生成工资报酬税务凭证。根据工资报酬支付申请审批表自动生成金蝶云税务凭证。

    参数：
        input_file: 工资报酬支付申请审批表 Excel 文件路径（.xlsx 或 .xls），必须提供。
        output_dir: 凭证输出目录，默认为输入文件所在目录。

    返回：
        执行结果的 JSON 字符串，包含 success、output_file、approval_count、entry_count、error_count、message。
        成功示例：{"success": true, "output_file": "...", "approval_count": 15, "entry_count": 45, "message": "生成完成！"}
        失败示例：{"success": false, "error": {"code": "FILE_NOT_FOUND", "message": "..."}}
    """
    if not input_file:
        return json.dumps(error_response(MissingParameterError(
            "invoke_salary_tax_voucher",
            "input_file",
        )), ensure_ascii=False)
    try:
        result = _run_salary_tax_voucher(
            input_file=input_file,
            output_dir=output_dir,
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        import traceback
        return json.dumps(error_response(SkillExecutionError(
            "invoke_salary_tax_voucher",
            reason=str(e),
            traceback=traceback.format_exc(),
        )), ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────
# 工具元数据（deep-agent 读取并注册到 LLM）
# ─────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "invoke_salary_tax_voucher",
            "description": (
                "生成工资报酬税务凭证。根据工资报酬支付申请审批表（金蝶云格式）自动生成税务凭证。"
                "支持派遣、代理、承揽、助残等多种业务类型，自动匹配账簿和客户，生成借贷分录。"
                "助残业务使用管理费用科目，其他业务使用主营业务成本科目。"
                "触发词：生成工资税务凭证、生成工资报酬税务凭证、X月工资凭证、工资税务凭证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_file": {
                        "type": "string",
                        "description": "工资报酬支付申请审批表 Excel 文件的完整路径（.xlsx 或 .xls），必填。"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "凭证输出目录，默认为输入文件所在目录"
                    }
                },
                "required": ["input_file"]
            }
        }
    }
]
