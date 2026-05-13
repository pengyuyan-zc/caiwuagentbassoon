# -*- coding: utf-8 -*-
"""
纯 Python ReAct Agent（无外部框架依赖，LangGraph 未安装时使用）
"""

from __future__ import annotations

import json
from pathlib import Path

from agent.helpers import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_API_URL,
    DEFAULT_MODEL,
    MAX_LOOP,
    _SKILLS_DIR,
    _load_tools_from_skills,
    _build_skill_system_prompt,
    _call_dashscope,
)


def _execute_tool(tool_name: str, args: dict) -> str:
    """根据工具名执行对应函数"""
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
                if isinstance(result, dict):
                    return json.dumps(result, ensure_ascii=False)
                return str(result)
            except Exception as e:
                import traceback
                return json.dumps({
                    "success": False,
                    "message": f"工具执行出错: {e}\n{traceback.format_exc()}"
                }, ensure_ascii=False)

    return json.dumps({"success": False, "message": f"未找到工具: {tool_name}"})


class SimpleReActAgent:
    """纯 Python ReAct Agent（无框架依赖）"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str = DASHSCOPE_API_KEY,
        api_url: str = DASHSCOPE_API_URL,
        max_loop: int = MAX_LOOP,
    ):
        self.model = model
        self.api_key = api_key
        self.api_url = api_url
        self.max_loop = max_loop
        self.system_prompt = _build_skill_system_prompt()
        self.tools = _load_tools_from_skills()

        print(f"[SimpleAgent] 模型: {self.model}")
        print(f"[SimpleAgent] 系统提示词长度: {len(self.system_prompt)} 字符")
        print(f"[SimpleAgent] 已加载 {len(self.tools)} 个工具")

    def invoke(self, input_dict: dict, config: dict = None) -> dict:
        """主入口。config 参数保留以兼容 LangGraph Agent 接口（此处忽略）。"""
        messages: list = input_dict.get("messages", [])
        if not messages:
            return {"messages": [{"role": "assistant", "content": "没有收到消息"}]}

        llm_messages = [{"role": "system", "content": self.system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue
            llm_messages.append({
                "role": role,
                "content": msg.get("content", ""),
            })

        step = 0
        while step < self.max_loop:
            step += 1
            response = _call_dashscope(
                messages=llm_messages,
                tools=self.tools,
                api_key=self.api_key,
                api_url=self.api_url,
                model=self.model,
            )

            if "tool_calls" not in response:
                llm_messages.append({"role": "assistant", "content": response.get("content", "")})
                return {"messages": llm_messages, "finished": True}

            llm_messages.append({
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": response["tool_calls"]
            })

            for tc in response["tool_calls"]:
                tool_name = tc["function"]["name"]
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)
                result_str = _execute_tool(tool_name, args)
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "name": tool_name,
                    "content": result_str,
                })

        final_content = (llm_messages[-1].get("content", "") +
                        "\n[Agent] 达到最大循环次数（工具调用未收敛）")
        llm_messages.append({"role": "assistant", "content": final_content})
        return {"messages": llm_messages, "finished": False}


def create_simple_agent(
    model: str = DEFAULT_MODEL,
    api_key: str = DASHSCOPE_API_KEY,
    api_url: str = DASHSCOPE_API_URL,
    max_loop: int = MAX_LOOP,
):
    return SimpleReActAgent(model=model, api_key=api_key, api_url=api_url, max_loop=max_loop)


def create_react_agent(
    model: str = DEFAULT_MODEL,
    api_key: str = DASHSCOPE_API_KEY,
    api_url: str = DASHSCOPE_API_URL,
    max_loop: int = MAX_LOOP,
):
    return create_simple_agent(model, api_key, api_url, max_loop)
