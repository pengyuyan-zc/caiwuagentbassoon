# -*- coding: utf-8 -*-
"""
知识库包

包含：
  - embedding.py: Embedding 模型封装
  - vector_store.py: 向量存储抽象层（ChromaDB / FAISS）
  - kb_manager.py: 知识库管理器（加载、分割、检索）
"""

from agent.knowledge.embedding import (
    get_embedding_model,
    reset_embedder,
    DashScopeEmbedder,
    LocalSentenceTransformerEmbedder,
    DashScopeReranker,
)
from agent.knowledge.vector_store import (
    VectorStore,
    ChromaStore,
    FaissStore,
    create_vector_store,
    Chunk,
)
from agent.knowledge.kb_manager import (
    KnowledgeBaseManager,
    get_kb_manager,
    reset_kb_manager,
)

__all__ = [
    "get_embedding_model",
    "reset_embedder",
    "DashScopeEmbedder",
    "LocalSentenceTransformerEmbedder",
    "DashScopeReranker",
    "VectorStore",
    "ChromaStore",
    "FaissStore",
    "create_vector_store",
    "Chunk",
    "KnowledgeBaseManager",
    "get_kb_manager",
    "reset_kb_manager",
]
