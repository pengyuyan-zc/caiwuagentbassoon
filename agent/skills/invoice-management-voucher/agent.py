# -*- coding: utf-8 -*-
from __future__ import annotations

"""
开票管理帐凭证生成 - Skill 执行入口（deep-agent 工具）

供 deep-agent 的 LLM 通过工具调用此 skill。

工具列表：
  - invoke_management_voucher: 生成开票管理帐凭证
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

def _run_management_voucher(
    input_file: str | Path,
    output_dir: str | Path | None = None,
    template_file: str | Path | None = None,
) -> dict[str, Any]:
    """
    生成开票管理帐凭证的内部实现。

    Args:
        input_file: 开票主体 Excel 文件路径（OA 开票申请数据）
        output_dir:  输出目录，默认同输入文件
        template_file: 凭证模板路径，默认在输入文件目录下查找含"管理"+"凭证"的文件

    Returns:
        dict，包含 success / output_file / voucher_count / line_count / message
    """
    import re as _re

    input_path = Path(input_file)
    if not input_path.exists():
        return error_response(FileNotFoundError(str(input_path)))

    out_dir = Path(output_dir) if output_dir else input_path.parent

    # 所有文件均在 skill 目录下自包含
    # 优先在 skill 目录搜索凭证模板
    if template_file and str(template_file).strip():
        tpl_path = Path(template_file)
    else:
        tpl_path = None
        dir_seen = set()
        for p in _SKILL_DIR.rglob("*.xlsx"):
            if p.name in dir_seen or p.name.startswith("~"):
                continue
            dir_seen.add(p.name)
            if "管理" in p.name and "凭证" in p.name:
                tpl_path = p
                break

    if not tpl_path or not tpl_path.exists():
        return {"success": False, "message": f"凭证模板不存在：{tpl_path}"}

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"管理帐凭证_{ts}.xlsx"

    # 调用 skill 目录下的脚本（使用中文参数名 --输入/--输出/--客户/--模板）
    script_path = _SKILL_DIR / "generate_voucher.py"
    if not script_path.exists():
        return {"success": False, "message": f"执行脚本不存在：{script_path}"}

    # 客户字典也在 skill 目录下
    cust_path = _SKILL_DIR / "客户明细管理帐.xlsx"
    if not cust_path.exists():
        return {"success": False, "message": f"客户字典不存在：{cust_path}"}

    args = [
        sys.executable,
        str(script_path),
        "--输入", str(input_path),
        "--输出", str(out_file),
        "--客户", str(cust_path),
        "--模板", str(tpl_path),
    ]

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        combined = (result.stdout or "") + (result.stderr or "")

        voucher_count = None
        line_count = None
        for line in combined.splitlines():
            m = _re.search(r"(\d+)\s*张凭证", line)
            if m:
                voucher_count = int(m.group(1))
            m = _re.search(r"(\d+)\s*条分录", line)
            if m:
                line_count = int(m.group(1))

        return {
            "success": result.returncode == 0,
            "output_file": str(out_file) if result.returncode == 0 else None,
            "voucher_count": voucher_count,
            "line_count": line_count,
            "message": combined,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "执行超时（120秒），请检查输入文件或减少数据量。"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ─────────────────────────────────────────────────────────────────────
# Deep-agent 工具定义（供 LLM 调用）
# ─────────────────────────────────────────────────────────────────────

def invoke_management_voucher(
    input_file: str,
    output_dir: str | None = None,
    template_file: str | None = None,
) -> str:
    """
    生成开票管理帐凭证。根据 OA 开票申请数据自动生成金蝶云管理帐凭证。

    参数：
        input_file: 开票主体 / OA 开票申请 Excel 文件路径（.xlsx 或 .xls），必须提供。
        output_dir: 凭证输出目录，默认为输入文件所在目录。
        template_file: 金蝶云管理帐凭证模板路径，默认自动在目录下搜索含"管理"+"凭证"的文件。

    返回：
        执行结果的 JSON 字符串，包含 success、output_file、voucher_count、line_count、message。
        成功示例：{"success": true, "output_file": "...", "voucher_count": 15, "line_count": 45, "message": "生成完成！"}
        失败示例：{"success": false, "error": {"code": "FILE_NOT_FOUND", "message": "..."}}
    """
    if not input_file:
        return json.dumps(error_response(MissingParameterError(
            "invoke_management_voucher",
            "input_file",
        )), ensure_ascii=False)
    try:
        result = _run_management_voucher(
            input_file=input_file,
            output_dir=output_dir,
            template_file=template_file,
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        import traceback
        err_msg = str(e)
        if "列" in err_msg or "column" in err_msg.lower() or isinstance(e, ValueError):
            return json.dumps(error_response(FileFormatError(
                input_file,
                expected_format="OA开票申请Excel",
                actual_format="缺少必要列",
            )), ensure_ascii=False)
        return json.dumps(error_response(SkillExecutionError(
            "invoke_management_voucher",
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
            "name": "invoke_management_voucher",
            "description": (
                "生成开票管理帐凭证。根据 OA 开票申请数据自动生成金蝶云管理帐凭证。"
                "凭证分录规则：借 1122 应收账款（按内部类型选子目）= 开票总额；"
                "贷 6001 主营业务收入（按内部类型选子目）= 不含税金额；"
                "贷 2221.01.02 销项税额（增值税金额>0时）= 增值税金额。"
                "账簿按开票主体区分（广东谊丰→501，其他→102）。"
                "当用户提到'开票管理帐凭证'、'生成开票管理帐凭证'、'X月开票管理帐凭证'时使用此工具。"
                "触发词：生成开票管理帐凭证、生成开票管理帐凭证、X月开票管理帐凭证、开票主体管理帐凭证、管理帐发票凭证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_file": {
                        "type": "string",
                        "description": "OA 开票申请 Excel 文件的完整路径（.xlsx 或 .xls）"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "凭证输出目录，默认为输入文件所在目录"
                    },
                    "template_file": {
                        "type": "string",
                        "description": "金蝶云管理帐凭证模板路径，默认自动搜索"
                    }
                },
                "required": ["input_file"]
            }
        }
    }
]
