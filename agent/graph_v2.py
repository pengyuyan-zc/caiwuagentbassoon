# -*- coding: utf-8 -*-
"""
LangGraph v2 - 多节点工作流 Agent（含 RAG 知识增强）

架构：
  start
    ↓  conditional_edges（route_start：判断是否需要 RAG）
  ┌──────────────────────────────────────┐
  │ 需要 RAG → rag_retrieve → model_node │
  │ 不需要 → model_node                  │
  └──────────────────────────────────────┘
    ↓
  model_node（ReAct 循环：LLM 判断是否调用工具）
    ↓  conditional_edges（根据 tool_calls 路由）
  ┌──────────────────────────────────────┐
  │ 有 tool_calls → tools_node → model_node │  （继续 ReAct 循环）
  │ 无 tool_calls 且 waiting_for_approval → human_node
  │ 无 tool_calls 且 无 waiting → output_node → END
  └──────────────────────────────────────┘
    ↓
  human_node（人工审批节点）
    ↓  conditional_edges
  ┌──────────────────────────────────────┐
  │ approved → output_node → END        │
  │ rejected → clarification_node → END  │
  │ 修改重试 → model_node（带着修改参数）    │
  └──────────────────────────────────────┘

Checkpoint 持久化：SqliteSaver（开发）/ MemorySaver（默认不可用时）

关键改进（相对于原 graph.py）：
  1. 独立的 human_approval_node + output_node
  2. 可插拔 checkpoint 持久化（SQLite / Memory）
  3. 多会话 thread_id 支持
  4. 节点级别状态序列化（支持审批预览）
  5. 工具结果通过 state["tool_results"] 共享，不再每次重新加载 tools
  6. RAG 知识增强节点（可选，通过 RAG_ENABLED 配置开启）
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated, TypedDict, Literal, Optional

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt

from agent.helpers import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_API_URL,
    DEFAULT_MODEL,
    MAX_LOOP,
    _load_tools_from_skills,
    _build_skill_system_prompt,
    _SKILLS_DIR,
    _call_dashscope,
)
from agent import config

# ── RAG 节点导入 ──────────────────────────────────────────────────────────
from agent.nodes.rag_node import (
    rag_retrieve_node,
    rag_routing_decision,
    should_use_rag,
)


# ══════════════════════════════════════════════════════════════════════════
# Agent State 定义
# ══════════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    # 消息历史
    messages: Annotated[list[dict], "append"]
    # 工具调用结果列表
    tool_results: Annotated[list[dict], "append"]
    # 执行步数
    step: Annotated[int, "increment"]

    # ── 流程控制字段 ──────────────────────────────────────────────────
    # ReAct 循环是否完成
    finished: bool
    # 是否等待人工审批
    waiting_for_approval: bool
    # 审批相关数据（供前端预览）
    approval_data: Optional[dict]
    # 审批动作（由 resume 时注入）
    approval_action: Optional[Literal["approve", "reject", "modify"]]
    # 审批携带的修改参数
    approval_modifications: Optional[dict]
    # 人工介入前的最后一条 assistant 消息（用于审批预览）
    last_assistant_msg: Optional[dict]

    # ── 执行轨迹（用于 trace）─────────────────────────────────────────
    node_path: Annotated[list[str], "append"]
    # 当前节点名称
    current_node: Optional[str]


# ══════════════════════════════════════════════════════════════════════════
# Checkpointer 工厂
# ══════════════════════════════════════════════════════════════════════════

def _build_checkpointer():
    """
    默认使用 SqliteSaver 持久化 checkpoint，重启服务也不会丢失会话。
    """
    sqlite_path = config.agent.sqlite_db_path
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(sqlite_path, check_same_thread=False)
        saver = SqliteSaver(conn)
        print(f"[Checkpointer] SQLite checkpoint 持久化: {sqlite_path}")
        return saver
    except ImportError:
        print("[Checkpointer] SqliteSaver 不可用，降级为 MemorySaver")
    except Exception as e:
        print(f"[Checkpointer] SQLite 初始化失败: {e}，降级为 MemorySaver")

    return MemorySaver()


# ══════════════════════════════════════════════════════════════════════════
# 工具执行（封装为节点）
# ══════════════════════════════════════════════════════════════════════════

def _execute_tool(tool_name: str, args: dict) -> str:
    """根据工具名执行对应函数，返回 JSON 字符串"""
    sys.stderr.write(f"[tools] 调用工具: {tool_name}  参数: {args}\n")
    sys.stderr.flush()

    for item in _SKILLS_DIR.iterdir():
        if not (item.is_dir() and not item.name.startswith("_")):
            continue
        agent_py = item / "agent.py"
        if not agent_py.exists():
            continue

        import importlib.util
        spec = importlib.util.spec_from_file_location(f"skill_{item.name}_agent", str(agent_py))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, tool_name):
            fn = getattr(mod, tool_name)
            try:
                result = fn(**args)
                return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            except Exception as e:
                import traceback
                return json.dumps({
                    "success": False,
                    "message": f"工具执行出错: {e}\n{traceback.format_exc()}"
                }, ensure_ascii=False)

    return json.dumps({"success": False, "message": f"未找到工具: {tool_name}"})


# ══════════════════════════════════════════════════════════════════════════
# 节点定义
# ══════════════════════════════════════════════════════════════════════════

def model_node(state: AgentState) -> AgentState:
    """
    LLM 推理节点（ReAct 核心）。
    负责：加载 system prompt + messages → 调用 DashScope → 返回响应。

    如果是 resume（approval_action 非空），则注入审批结果到 messages。
    """
    messages = state["messages"]
    step = state.get("step", 0)
    tool_results = state.get("tool_results", [])
    node_path = state.get("node_path", [])

    sys.stderr.write(f"[model_node] step={step}, waiting={state.get('waiting_for_approval')}, "
                     f"approval_action={state.get('approval_action')}\n")
    sys.stderr.flush()

    # ── 处理人工审批后的 resume ────────────────────────────────────────
    approval_action = state.get("approval_action")
    if approval_action:
        sys.stderr.write(f"[model_node] 收到人工审批: {approval_action}, modifications={state.get('approval_modifications')}\n")

        # 将审批结果注入消息，通知 LLM
        approval_msg = {
            "role": "user",
            "content": (
                f"【系统通知】人工审批结果：{approval_action}。"
                f"{' 已按以下修改重试：' + json.dumps(state.get('approval_modifications'), ensure_ascii=False) if state.get('approval_modifications') else ''}"
                f"请根据审批结果{'重新生成凭证' if approval_action == 'modify' else '继续'}。"
            )
        }
        messages = messages + [approval_msg]

        # 审批数据清除（避免下次循环误读）
        waiting_for_approval = False
        approval_data = None
        approval_action = None
        approval_modifications = None
    else:
        waiting_for_approval = False
        approval_data = None
        approval_modifications = None

    # ── 步数限制 ─────────────────────────────────────────────────────
    if step >= MAX_LOOP:
        return {
            "messages": messages + [{"role": "assistant", "content": "[Agent] 达到最大循环次数，工具调用未收敛。"}],
            "tool_results": tool_results,
            "step": step,
            "finished": True,
            "waiting_for_approval": False,
            "approval_data": None,
            "node_path": node_path + ["model_node"],
            "current_node": "model_node",
        }

    try:
        tools = _load_tools_from_skills()
        system_prompt = _build_skill_system_prompt()

        llm_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            if msg.get("role") != "system":
                llm_messages.append({"role": msg["role"], "content": msg.get("content", "")})

        response = _call_dashscope(
            messages=llm_messages,
            tools=tools,
            api_key=DASHSCOPE_API_KEY,
            api_url=DASHSCOPE_API_URL,
        )

        new_messages = messages + [response]

        if "tool_calls" not in response:
            # LLM 无需工具 → 检查是否需要人工审批
            # 规则：上一轮有凭证生成工具调用（tool_name 包含 voucher/invoice），
            #      且 human_approval.enabled = True → 进入审批节点
            last_tool = None
            if tool_results:
                last_tool = tool_results[-1].get("tool", "")

            need_approval = (
                config.human_approval.enabled
                and config.human_approval.force_for_vouchers
                and last_tool is not None
                and any(kw in last_tool.lower() for kw in ["voucher", "invoice", "management_voucher"])
            )

            if need_approval:
                # 构建审批数据：从 tool_results 中提取凭证信息
                approval_data = _build_approval_data(tool_results, response)
                return {
                    "messages": new_messages,
                    "tool_results": tool_results,
                    "step": step + 1,
                    "finished": False,
                    "waiting_for_approval": True,
                    "approval_data": approval_data,
                    "approval_action": None,
                    "approval_modifications": None,
                    "last_assistant_msg": response,
                    "node_path": node_path + ["model_node"],
                    "current_node": "model_node",
                }
            else:
                return {
                    "messages": new_messages,
                    "tool_results": tool_results,
                    "step": step + 1,
                    "finished": False,  # 进入 output_node
                    "waiting_for_approval": False,
                    "approval_data": None,
                    "node_path": node_path + ["model_node"],
                    "current_node": "model_node",
                }

        # 有 tool_calls → 进入 tools_node
        return {
            "messages": new_messages,
            "tool_results": tool_results,
            "step": step + 1,
            "finished": False,
            "waiting_for_approval": False,
            "approval_data": None,
            "node_path": node_path + ["model_node"],
            "current_node": "model_node",
        }

    except Exception as e:
        import traceback
        error_msg = f"LLM 调用出错: {e}\n{traceback.format_exc()}"
        sys.stderr.write(f"[model_node] 错误: {error_msg}\n")
        return {
            "messages": messages + [{"role": "assistant", "content": error_msg}],
            "tool_results": tool_results,
            "step": step + 1,
            "finished": True,
            "waiting_for_approval": False,
            "approval_data": None,
            "node_path": node_path + ["model_node"],
            "current_node": "model_node",
        }


def tools_node(state: AgentState) -> AgentState:
    """
    工具执行节点。
    遍历 last assistant message 中的所有 tool_calls，依次执行。
    """
    messages = state["messages"]
    tool_results = state.get("tool_results", [])
    node_path = state.get("node_path", [])
    last_msg = state["messages"][-1]
    tool_calls = last_msg.get("tool_calls", [])

    sys.stderr.write(f"[tools_node] 执行 {len(tool_calls)} 个工具调用\n")
    sys.stderr.flush()

    for tc in tool_calls:
        tool_name = tc["function"]["name"]
        args = tc["function"]["arguments"]
        if isinstance(args, str):
            args = json.loads(args)

        tool_result_str = _execute_tool(tool_name, args)

        # 记录工具调用结果
        try:
            parsed = json.loads(tool_result_str)
        except Exception:
            parsed = {"raw": tool_result_str}

        tool_msg = {
            "role": "tool",
            "tool_call_id": tc.get("id", ""),
            "name": tool_name,
            "content": tool_result_str,
        }
        messages = messages + [tool_msg]
        tool_results = tool_results + [{
            "tool": tool_name,
            "args": args,
            "result": parsed,
        }]

        # 如果工具返回 success=false，直接结束，不继续循环
        if isinstance(parsed, dict) and parsed.get("success") is False:
            fail_msg = parsed.get("message", "操作失败，请重试。")
            messages = messages + [{"role": "assistant", "content": fail_msg}]
            sys.stderr.write(f"[tools_node] 工具 {tool_name} 返回失败: {fail_msg}\n")
            return {
                "messages": messages,
                "tool_results": tool_results,
                "step": state["step"],
                "finished": True,
                "waiting_for_approval": False,
                "approval_data": None,
                "node_path": node_path + ["tools_node"],
                "current_node": "tools_node",
            }

    return {
        "messages": messages,
        "tool_results": tool_results,
        "step": state["step"],
        "finished": False,
        "waiting_for_approval": state.get("waiting_for_approval", False),
        "approval_data": state.get("approval_data"),
        "node_path": node_path + ["tools_node"],
        "current_node": "tools_node",
    }


def human_approval_node(state: AgentState) -> AgentState:
    """
    人工审批节点。

    此节点由 model_node 在凭证生成完成后调用，进入等待状态。
    前端通过 resume（发送审批消息）来继续执行。

    路由逻辑在 conditional_edges 中处理。
    """
    node_path = state.get("node_path", [])
    sys.stderr.write(f"[human_approval_node] 进入人工审批，等待前端确认...\n")
    sys.stderr.flush()

    # 本节点不执行任何操作，仅作为状态标记
    # 实际路由由 conditional_edges 根据 approval_action 判断
    return {
        "messages": state["messages"],
        "tool_results": state.get("tool_results", []),
        "step": state["step"],
        "finished": False,
        "waiting_for_approval": True,
        "approval_data": state.get("approval_data"),
        "approval_action": state.get("approval_action"),
        "approval_modifications": state.get("approval_modifications"),
        "node_path": node_path + ["human_approval_node"],
        "current_node": "human_approval_node",
    }


def output_node(state: AgentState) -> AgentState:
    """
    输出节点：生成最终回复和下载链接。
    """
    node_path = state.get("node_path", [])
    tool_results = state.get("tool_results", [])
    messages = state["messages"]

    # 从 tool_results 提取凭证信息
    voucher_result = None
    for tr in reversed(tool_results):
        if isinstance(tr.get("result"), dict) and tr["result"].get("output_file"):
            voucher_result = tr["result"]
            break

    download_url = None
    if voucher_result and voucher_result.get("output_file"):
        import urllib.parse
        safe_path = voucher_result["output_file"].replace("\\", "/")
        encoded_path = urllib.parse.quote(safe_path)
        download_url = f"http://127.0.0.1:{config.server.port}/download?file={encoded_path}"

    reply_parts = []
    if voucher_result:
        reply_parts.append(
            f"凭证生成完成！\n"
            f"• 凭证数量：{voucher_result.get('voucher_count', 0)} 张\n"
            f"• 分录数量：{voucher_result.get('line_count', 0)} 条\n\n"
            f"[点击下载凭证文件]({download_url})"
        )

    # LLM 的最终回复
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            if not voucher_result:
                reply_parts.append(msg["content"])
            break

    final_reply = "\n\n".join(reply_parts) if reply_parts else "处理完成。"

    sys.stderr.write(f"[output_node] 完成，reply 长度={len(final_reply)}\n")
    return {
        "messages": messages + [{"role": "assistant", "content": final_reply}],
        "tool_results": tool_results,
        "step": state["step"],
        "finished": True,
        "waiting_for_approval": False,
        "approval_data": None,
        "node_path": node_path + ["output_node"],
        "current_node": "output_node",
    }


# ══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════════════

def _build_approval_data(tool_results: list[dict], last_assistant_msg: dict) -> dict:
    """从工具结果构建审批预览数据"""
    # 找最后一个凭证生成工具的结果
    voucher_result = None
    for tr in reversed(tool_results):
        if isinstance(tr.get("result"), dict) and tr["result"].get("output_file"):
            voucher_result = tr["result"]
            break

    if not voucher_result:
        return {}

    return {
        "voucher_count": voucher_result.get("voucher_count", 0),
        "line_count": voucher_result.get("line_count", 0),
        "output_file": voucher_result.get("output_file", ""),
        "message": voucher_result.get("message", ""),
        "last_tool": tool_results[-1].get("tool") if tool_results else None,
    }


# ══════════════════════════════════════════════════════════════════════════
# 条件路由边
# ══════════════════════════════════════════════════════════════════════════

def route_after_model(state: AgentState) -> Literal["tools", "human_approval", "output"]:
    """
    model_node 之后的路由：
      - 有 tool_calls → tools_node
      - 无 tool_calls 且 waiting_for_approval → human_approval_node
      - 无 tool_calls 且 无 waiting → output_node
    """
    last_msg = state["messages"][-1]
    if last_msg.get("tool_calls"):
        return "tools"
    if state.get("waiting_for_approval"):
        return "human_approval"
    return "output"


def route_after_tools(state: AgentState) -> Literal["model", "human_approval", "output"]:
    """
    tools_node 之后的路由：
      - finished=True → output_node
      - waiting_for_approval=True → human_approval_node
      - 否则 → model_node（继续 ReAct 循环）
    """
    if state.get("finished"):
        return "output"
    if state.get("waiting_for_approval"):
        return "human_approval"
    return "model"


def route_after_human(state: AgentState) -> Literal["model", "output"]:
    """
    human_approval_node 之后的路由：
      - approved / modify → model_node（带参数重试）
      - rejected → output_node（结束）
    """
    action = state.get("approval_action")
    if action in ("approve", "modify"):
        return "model"
    return "output"


# ══════════════════════════════════════════════════════════════════════════
# 构建 LangGraph
# ══════════════════════════════════════════════════════════════════════════

def create_graph_v2():
    """
    构建并编译 LangGraph v2 多节点工作流。

    当 RAG_ENABLED=true 时，会在 model_node 前添加 rag_retrieve 节点，
    根据用户问题内容自动判断是否需要检索知识库。
    """
    graph = StateGraph(AgentState)

    # 注册节点
    graph.add_node("model", model_node)
    graph.add_node("tools", tools_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("output", output_node)

    # ── RAG 节点（可选）────────────────────────────────────────────────────
    if config.rag.enabled:
        graph.add_node("rag_retrieve", rag_retrieve_node)

        # START → 条件路由（判断是否需要 RAG）
        graph.add_conditional_edges(
            START,
            rag_routing_decision,
            {
                "rag_retrieve": "rag_retrieve",
                "model": "model",
            }
        )

        # rag_retrieve → model（检索后进入正常流程）
        graph.add_edge("rag_retrieve", "model")
    else:
        # RAG 未启用，直接进入 model
        graph.set_entry_point("model")

    # model 节点条件边
    graph.add_conditional_edges(
        "model",
        route_after_model,
        {
            "tools": "tools",
            "human_approval": "human_approval",
            "output": "output",
        }
    )

    # tools 节点条件边
    graph.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "model": "model",
            "human_approval": "human_approval",
            "output": "output",
        }
    )

    # human_approval 节点条件边
    graph.add_conditional_edges(
        "human_approval",
        route_after_human,
        {
            "model": "model",
            "output": "output",
        }
    )

    # output 是终点
    graph.add_edge("output", END)

    # 编译
    checkpointer = _build_checkpointer()
    app = graph.compile(checkpointer=checkpointer)

    # 打印节点信息
    print("=" * 60)
    print("  LangGraph v2 - 多节点工作流")
    print("=" * 60)
    print("  节点列表：")
    nodes = ["model", "tools", "human_approval", "output"]
    if config.rag.enabled:
        nodes.insert(0, "rag_retrieve")
    for node in nodes:
        print(f"    - {node}")
    print("  Checkpointer:", type(checkpointer).__name__)
    print("  Human Approval:", "已启用" if config.human_approval.enabled else "未启用")
    print("  RAG:", "已启用" if config.rag.enabled else "未启用")
    print("=" * 60)

    return app


# ══════════════════════════════════════════════════════════════════════════
# 便捷入口（兼容原有 API）
# ══════════════════════════════════════════════════════════════════════════

_graph_instance = None


def get_graph_v2():
    """获取 graph v2 单例（延迟初始化）"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = create_graph_v2()
    return _graph_instance


def create_react_agent_v2(
    model: str = DEFAULT_MODEL,
    api_key: str = DASHSCOPE_API_KEY,
    api_url: str = DASHSCOPE_API_URL,
    max_loop: int = MAX_LOOP,
):
    """
    创建 v2 Agent（多节点工作流）。
    兼容原有接口，finance_agent.py 可直接替换调用。
    """
    return get_graph_v2()
