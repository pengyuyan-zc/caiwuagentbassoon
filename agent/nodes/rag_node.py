# -*- coding: utf-8 -*-
"""
RAG 检索节点

作为 LangGraph v2 中的可选节点，嵌入到工作流中。
当用户问题涉及财务知识（科目、凭证规则、税务政策等）时，
从向量知识库检索相关片段，注入到 LLM 上下文。

使用方式：
    from agent.nodes.rag_node import rag_retrieve_node, should_use_rag

    # 在 graph_v2 中引入
    graph.add_node("rag_retrieve", rag_retrieve_node)
    # 在 model_node 之前添加条件路由边
"""

from __future__ import annotations

from typing import TypedDict, Optional, Literal
from agent import config


# ══════════════════════════════════════════════════════════════════════════
# RAG State 扩展
# ══════════════════════════════════════════════════════════════════════════

class RAGState(TypedDict, total=False):
    """可选的 RAG 相关状态字段（混入 AgentState）"""
    rag_enabled: bool
    rag_query: Optional[str]
    rag_context: Optional[str]
    rag_results: Optional[list[dict]]


# ══════════════════════════════════════════════════════════════════════════
# 意图判断：是否需要 RAG
# ══════════════════════════════════════════════════════════════════════════

# 低成本关键词规则引擎（代替 LLM 意图分类节点）
RAG_KEYWORDS = [
    "科目", "分录", "凭证", "规则", "如何做", "怎么做", "税务",
    "税率", "销项税", "进项税", "增值税", "企业所得税", "发票",
    "入账", "做账", "记账", "账户", "借贷", "余额", "结转",
    "汇算", "抵扣", "申报", "金蝶", "账务处理", "会计处理",
    "说明", "解释", "请问", "什么叫", "什么是",
]

RAG_TRIGGER_KEYWORDS = [
    "怎么入账", "如何做分录", "科目是什么", "凭证规则", "税务处理",
    "税率多少", "开票规则", "做账方法", "记账凭证", "分录借贷方向",
]


def should_use_rag(query: str) -> bool:
    """
    判断用户问题是否需要 RAG 知识检索。
    使用轻量关键词匹配（零 LLM 调用成本）。

    Returns:
        True: 需要 RAG 检索
        False: 不需要，直接进入 normal ReAct
    """
    if not config.rag.enabled:
        return False

    query_lower = query.lower()
    # 精确匹配触发词
    for kw in RAG_TRIGGER_KEYWORDS:
        if kw in query_lower:
            return True
    # 统计关键词命中数
    hits = sum(1 for kw in RAG_KEYWORDS if kw in query_lower)
    return hits >= 2


def rag_routing_decision(state: dict) -> Literal["rag_retrieve", "model"]:
    """
    LangGraph 条件边：根据 state 判断是否进入 RAG 检索节点。

    进入条件：
      1. rag.enabled = True
      2. 用户消息包含财务知识关键词
      3. 且不是直接的文件凭证生成请求
    """
    if not config.rag.enabled:
        return "model"

    # 从最新消息中提取用户 query
    messages = state.get("messages", [])
    user_query = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_query = msg.get("content", "")
            break

    # 判断是否需要 RAG
    if should_use_rag(user_query):
        return "rag_retrieve"
    return "model"


# ══════════════════════════════════════════════════════════════════════════
# RAG 检索节点
# ══════════════════════════════════════════════════════════════════════════

def rag_retrieve_node(state: dict) -> dict:
    """
    RAG 检索节点：从知识库检索相关片段，注入上下文。
    """
    if not config.rag.enabled:
        return state

    # 提取用户问题
    messages = state.get("messages", [])
    user_query = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_query = msg.get("content", "")
            break

    if not user_query:
        return state

    # 检索
    try:
        from agent.knowledge.kb_manager import get_kb_manager
        kb = get_kb_manager()
        results = kb.retrieve(user_query, top_k=config.rag.top_k)
        context = kb.retrieve_as_context(user_query)

        state["rag_enabled"] = True
        state["rag_query"] = user_query
        state["rag_context"] = context
        state["rag_results"] = results

        # 将检索结果注入到 system prompt（通过修改最新 user message）
        if context:
            # 追加到最后一条 user message
            messages[-1]["content"] = (
                f"{user_query}\n\n"
                f"【系统提示：以下是与你的问题相关的财务知识，请结合这些知识回答。】\n"
                f"{context}\n"
            )

    except Exception as e:
        import sys
        sys.stderr.write(f"[rag_retrieve_node] 检索失败: {e}\n")
        state["rag_enabled"] = False
        state["rag_context"] = None
        state["rag_results"] = []

    return state
