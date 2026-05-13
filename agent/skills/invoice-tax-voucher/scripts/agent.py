# -*- coding: utf-8 -*-
from __future__ import annotations

"""
开票税务凭证生成 - Skill 执行入口（deep-agent 工具）

供 deep-agent 的 LLM 通过工具调用此 skill。

工具列表：
  - invoke_invoice_voucher: 生成开票凭证
"""

import datetime
from pathlib import Path
from typing import Any

import sys as _sys

_SKILL_DIR = Path(__file__).parent
_PROJECT_ROOT = _SKILL_DIR.parent.parent

if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SKILL_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SKILL_DIR))


# ─────────────────────────────────────────────────────────────────────
# 业务函数（实际执行逻辑）
# ─────────────────────────────────────────────────────────────────────

def _run_invoice_voucher(
    input_file: str | Path,
    output_dir: str | Path | None = None,
    voucher_type: str = "税务",
) -> dict[str, Any]:
    """
    生成开票凭证的内部实现。

    Args:
        input_file: 开票主体 Excel 文件路径
        output_dir: 输出目录，默认同输入文件
        voucher_type: 凭证类型，"税务"（默认）或 "管理帐"

    Returns:
        dict，包含 success / output_file / voucher_count / line_count / message
    """
    if voucher_type == "管理帐":
        from 开票主体税务凭证生成_管理帐 import main as _main_glz
        import argparse as _argparse
        import io as _io
        import sys as _sys

        old_stdout = _sys.stdout
        old_stderr = _sys.stderr
        captured = _io.StringIO()
        try:
            _sys.stdout = _io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8")
            _sys.stderr = _io.TextIOWrapper(_sys.stderr.buffer, encoding="utf-8")
        except Exception:
            pass

        input_path = Path(input_file)
        out_dir = Path(output_dir) if output_dir else input_path.parent

        import tempfile, os, subprocess, sys as _sys2
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = out_dir / f"管理帐凭证_{ts}.xlsx"

        args = [
            _sys2.executable,
            str(Path(__file__).parent / "开票主体税务凭证生成_管理帐.py"),
            "--输入", str(input_path),
            "--模板", str(input_path.parent / "202510月凭证-管理.xlsx"),
            "--输出", str(out_file),
        ]
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8",
                timeout=120
            )
            return {
                "success": result.returncode == 0,
                "output_file": str(out_file),
                "voucher_count": None,
                "line_count": None,
                "message": result.stdout + result.stderr,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}
        finally:
            _sys.stdout = old_stdout
            _sys.stderr = old_stderr
    else:
        from 开票主体税务凭证生成 import generate_invoice_voucher
        input_path = Path(input_file)
        out_dir = Path(output_dir) if output_dir else input_path.parent

        # 诊断：检查文件头魔数
        if input_path.exists():
            header = input_path.read_bytes()[:8]
            print(f"[_run_invoice_voucher] input={input_path}  size={input_path.stat().st_size}")
            print(f"[_run_invoice_voucher] 文件头魔数: {header.hex()}  (pk=50 4b 3e 60 为有效xlsx)")
            if not header.startswith(b"PK"):
                print(f"[_run_invoice_voucher] 警告: 文件不是标准 xlsx！可能是 csv/html/文本")
                # 尝试当作 CSV 或 HTML 表格读取
                try:
                    text = input_path.read_text(encoding="utf-8", errors="replace")
                    if text.strip().startswith("<"):
                        print(f"[_run_invoice_voucher] 检测为 HTML，内容前100字符: {text[:100]}")
                    else:
                        lines = text.split("\n")
                        print(f"[_run_invoice_voucher] 检测为纯文本，共 {len(lines)} 行，前3行: {lines[:3]}")
                except Exception as e_text:
                    print(f"[_run_invoice_voucher] 文本读取失败: {e_text}")

        return generate_invoice_voucher(input_path, out_dir)


# ─────────────────────────────────────────────────────────────────────
# Deep-agent 工具定义（供 LLM 调用）
# ─────────────────────────────────────────────────────────────────────

def invoke_invoice_voucher(
    input_file: str,
    output_dir: str | None = None,
    voucher_type: str = "税务",
) -> str:
    """
    生成开票主体凭证。根据用户上传的Excel文件并请求生成凭证时使用。

    参数：
        input_file: 开票主体 Excel 文件路径（.xlsx 或 .xls），必须提供。
        output_dir: 凭证输出目录，默认为输入文件所在目录。
        voucher_type: 凭证类型，"税务"（默认）或 "管理帐"。
                      当用户在 管理帐 目录下操作或提到"管理帐凭证"时使用 "管理帐"。

    返回：
        执行结果的 JSON 字符串，包含 success、output_file、voucher_count、line_count、message。
        成功示例：{"success": true, "output_file": "...", "voucher_count": 15, "line_count": 45, "message": "生成完成！"}
        失败示例：{"success": false, "message": "错误原因"}
    """
    try:
        result = _run_invoice_voucher(
            input_file=input_file,
            output_dir=output_dir,
            voucher_type=voucher_type,
        )
        import json
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        import traceback
        import json
        err_msg = str(e)
        # ValueError 通常是列缺失 / 文件格式错误，直接返回给用户（纯文本，避免 LLM 误解释）
        if isinstance(e, ValueError) or "列" in err_msg or "column" in err_msg.lower():
            return json.dumps({
                "success": False,
                "message": (
                    "上传的文件格式不对：缺少必要的数据列（审批编号、客户/项目名称、开票总额等）。"
                    "请确认上传的是金蝶云导出的【开票主体Excel】文件，"
                    "而不是凭证明细模板或其他格式的文件。"
                )
            }, ensure_ascii=False)
        return json.dumps({
            "success": False,
            "message": f"执行失败: {e}\n{traceback.format_exc()}"
        }, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────
# 工具元数据（deep-agent 读取并注册到 LLM）
# ─────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "invoke_invoice_voucher",
            "description": (
                "生成开票主体凭证。根据用户上传的Excel文件（金蝶云格式）自动生成凭证Excel。"
                "凭证类型：voucher_type='税务' 生成税务帐凭证（凭证字=记，账簿按模板默认值）；"
                "voucher_type='管理帐' 生成管理帐凭证（使用 管理帐/202510月凭证-管理.xlsx 模板，"
                "凭证字=PZZ1，账簿按开票主体自动区分）。"
                "当用户在'管理帐'目录或提到'管理帐凭证'时，使用 voucher_type='管理帐'。"
                "触发词：生成开票凭证、生成税务凭证、X月开票凭证、开票主体凭证、发票凭证、生成凭证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input_file": {
                        "type": "string",
                        "description": "开票主体Excel文件的完整路径（.xlsx 或 .xls）"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "凭证输出目录，默认为输入文件所在目录"
                    },
                    "voucher_type": {
                        "type": "string",
                        "enum": ["税务", "管理帐"],
                        "description": "凭证类型：'税务'（默认）或'管理帐'"
                    }
                },
                "required": ["input_file"]
            }
        }
    }
]
