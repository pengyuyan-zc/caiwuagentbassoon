# -*- coding: utf-8 -*-
"""
LangGraph ReAct Agent 实现

使用 LangGraph StateGraph 构建 ReAct 循环：
  start → model_call → [has_tool_calls] → tool_execution → model_call / END
"""

from __future__ import annotations

import json
from typing import Annotated, TypedDict, Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

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


# ══════════════════════════════════════════════════════════════════════════
# State 定义
# ══════════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    messages: Annotated[list[dict], "append"]
    tool_results: Annotated[list[dict], "append"]
    step: Annotated[int, "increment"]
    finished: bool


# ══════════════════════════════════════════════════════════════════════════
# 工具执行
# ══════════════════════════════════════════════════════════════════════════

def _execute_tool(tool_name: str, args: dict) -> str:
    """根据工具名执行对应函数，返回 JSON 字符串（供 LLM 解析）。"""
    import sys as _sys
    _sys.stderr.write(f"[tools] 调用工具: {tool_name}  参数: {args}\n")
    _sys.stderr.flush()
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
                return json.dumps({"success": False, "message": f"工具执行出错: {e}\n{traceback.format_exc()}"}, ensure_ascii=False)

    return json.dumps({"success": False, "message": f"未找到工具: {tool_name}"}, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════
# LangGraph 节点
# ══════════════════════════════════════════════════════════════════════════

def tools_call_node(state: AgentState) -> AgentState:
    """调用 LLM，判断是否需要执行工具"""
    messages = state["messages"]
    step = state.get("step", 0)
    tool_results = state.get("tool_results", [])

    if step >= MAX_LOOP:
        return {
            "messages": messages + [{"role": "assistant", "content": "[Agent] 达到最大循环次数，工具调用未收敛。"}],
            "tool_results": tool_results,
            "step": step,
            "finished": True,
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

        messages = messages + [response]

        if "tool_calls" not in response:
            return {
                "messages": messages,
                "tool_results": tool_results,
                "step": step + 1,
                "finished": True,
            }

        return {
            "messages": messages,
            "tool_results": tool_results,
            "step": step + 1,
            "finished": False,
        }

    except Exception as e:
        import traceback
        error_msg = f"LLM 调用出错: {e}\n{traceback.format_exc()}"
        return {
            "messages": messages + [{"role": "assistant", "content": error_msg}],
            "tool_results": tool_results,
            "step": step + 1,
            "finished": True,
        }


def should_continue(state: AgentState) -> Literal["tools", "END"]:
    """路由：判断继续工具调用还是结束"""
    if state["finished"]:
        return END
    last_msg = state["messages"][-1]
    if last_msg.get("tool_calls"):
        return "tools"
    return END


def tools_node(state: AgentState) -> AgentState:
    """执行工具节点"""
    last_msg = state["messages"][-1]
    tool_calls = last_msg.get("tool_calls", [])

    for tc in tool_calls:
        tool_name = tc["function"]["name"]
        args = tc["function"]["arguments"]
        if isinstance(args, str):
            args = json.loads(args)

        tool_result_str = _execute_tool(tool_name, args)
        tool_msg = {
            "role": "tool",
            "tool_call_id": tc.get("id", ""),
            "name": tool_name,
            "content": tool_result_str,
        }
        state["messages"].append(tool_msg)
        state["tool_results"].append({
            "tool": tool_name,
            "args": args,
            "result": tool_result_str,
        })

        # 如果工具返回 success=false，直接结束，不要再让 LLM 重新解释
        try:
            parsed = json.loads(tool_result_str)
            if isinstance(parsed, dict) and parsed.get("success") is False:
                fail_msg = parsed.get("message", "操作失败")
                state["messages"].append({
                    "role": "assistant",
                    "content": fail_msg
                })
                state["finished"] = True
                return state
        except Exception:
            pass  # 非 JSON，继续正常流程

    return state


# ══════════════════════════════════════════════════════════════════════════
# 构建 LangGraph
# ══════════════════════════════════════════════════════════════════════════

def create_langgraph_agent(
    model: str = DEFAULT_MODEL,
    api_key: str = DASHSCOPE_API_KEY,
    api_url: str = DASHSCOPE_API_URL,
    max_loop: int = MAX_LOOP,
):
    """创建 LangGraph ReAct Agent"""
    graph = StateGraph(AgentState)
    graph.add_node("model", tools_call_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("model")
    graph.add_conditional_edges("model", should_continue, {
        "tools": "tools",
        END: END,
    })
    graph.add_edge("tools", "model")

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def create_react_agent(
    model: str = DEFAULT_MODEL,
    api_key: str = DASHSCOPE_API_KEY,
    api_url: str = DASHSCOPE_API_URL,
    max_loop: int = MAX_LOOP,
):
    return create_langgraph_agent(model, api_key, api_url, max_loop)
