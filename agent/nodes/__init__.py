# -*- coding: utf-8 -*-
"""
节点包

包含 LangGraph v2 各节点的独立实现文件。
当前 graph_v2.py 中节点以内联方式定义，后续可拆分为独立文件。

预计拆分结构：
  nodes/
    __init__.py
    intent_classify.py   # 意图分类（可选，用轻量规则替代 LLM 节点）
    invoice_node.py      # 开票凭证生成节点
    human_approval.py   # 人工审批节点
    rag_node.py         # RAG 检索节点（Phase 2）
"""

from agent.graph_v2 import (
    model_node,
    tools_node,
    human_approval_node,
    output_node,
    route_after_model,
    route_after_tools,
    route_after_human,
)

__all__ = [
    "model_node",
    "tools_node",
    "human_approval_node",
    "output_node",
    "route_after_model",
    "route_after_tools",
    "route_after_human",
]
