# -*- coding: utf-8 -*-
"""
Embedding 模型封装

支持两种模式：
  1. DashScope API（text-embedding-v3）- 默认，需 API Key
  2. 本地 sentence-transformers - 离线、无 API 成本

使用方式：
    from agent.knowledge.embedding import get_embedding_model

    embedder = get_embedding_model()   # 根据配置自动选择
    vectors = embedder.embed(["hello world"])
"""

from __future__ import annotations

import os
import json
import requests
from pathlib import Path
from typing import Optional

from agent import config


# ══════════════════════════════════════════════════════════════════════════
# 基础接口
# ══════════════════════════════════════════════════════════════════════════

class Embedder:
    """Embedding 模型抽象接口"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表转为向量列表"""
        raise NotImplementedError

    def embed_single(self, text: str) -> list[float]:
        """将单条文本转为向量"""
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        """向量维度"""
        raise NotImplementedError

    def close(self):
        """关闭资源（如有）"""
        pass


# ══════════════════════════════════════════════════════════════════════════
# DashScope API Embedding
# ══════════════════════════════════════════════════════════════════════════

class DashScopeEmbedder(Embedder):
    """
    通义千问 DashScope Embedding API
    模型：text-embedding-v3（1536维）

    环境变量：
        DASHSCOPE_API_KEY
        DASHSCOPE_EMBEDDING_URL（可选，默认使用标准端点）
        DASHSCOPE_EMBEDDING_MODEL（可选，默认 text-embedding-v3）
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-v3",
        api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
        batch_size: int = 25,
    ):
        self.api_key = api_key or config.dashscope.api_key
        self.model = model
        self.api_url = api_url
        self.batch_size = batch_size
        self._dimension = 1536 if model == "text-embedding-v3" else 1024

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量 embedding，每次最多 batch_size 条"""
        results = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            batch_vectors = self._embed_batch(batch)
            results.extend(batch_vectors)
        return results

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """单批次 embedding 调用"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": {"texts": texts},
        }

        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        result = resp.json()

        if "output" not in result or "embeddings" not in result["output"]:
            raise RuntimeError(f"DashScope embedding 返回异常: {result}")

        embeddings = result["output"]["embeddings"]
        return [item["embedding"] for item in embeddings]


# ══════════════════════════════════════════════════════════════════════════
# 本地 sentence-transformers Embedding
# ══════════════════════════════════════════════════════════════════════════

class LocalSentenceTransformerEmbedder(Embedder):
    """
    本地 sentence-transformers 模型
    优势：离线可用、无 API 成本、响应更快

    安装：pip install sentence-transformers
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers 未安装。\n"
                "  安装命令：pip install sentence-transformers\n"
                "  或切换到 DashScope API 模式（DASHSCOPE_EMBEDDING_MODEL=text-embedding-v3）"
            )

        self.model = SentenceTransformer(model_name)
        self._dimension = self.model.get_sentence_embedding_dimension()

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [row.tolist() for row in embeddings]


# ══════════════════════════════════════════════════════════════════════════
# Rerank 模型（可选）
# ══════════════════════════════════════════════════════════════════════════

class DashScopeReranker:
    """
    通义千问重排序模型

    安装 rerank 模型后，对检索结果重排序以提升相关度。
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gte-rerank"):
        self.api_key = api_key or config.dashscope.api_key
        self.model = model

    def rerank(
        self,
        query: str,
        candidates: list[str],
        top_n: int = 5,
    ) -> list[dict]:
        """
        对候选文档重排序，返回最相关的 top_n 条。

        Returns:
            [{"index": 0, "text": "...", "score": 0.95}, ...]
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": {"query": query, "documents": candidates},
            "parameters": {"top_n": top_n},
        }

        try:
            resp = requests.post(
                "https://dashscope.aliyuncs.com/api/v1/services/retrieval/text-generation/rerank",
                json=payload,
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("output", {}).get("results", [])
        except Exception as e:
            import sys
            sys.stderr.write(f"[Reranker] 调用失败: {e}，跳过重排序\n")
            return [{"index": i, "text": c, "score": 1.0 / (i + 1)} for i, c in enumerate(candidates[:top_n])]


# ══════════════════════════════════════════════════════════════════════════
# Embedder 工厂函数
# ══════════════════════════════════════════════════════════════════════════

_cached_embedder: Optional[Embedder] = None


def get_embedding_model(force_local: bool = False) -> Embedder:
    """
    根据配置返回合适的 Embedder 实例。

    优先级：
      1. sentence-transformers（force_local=True 时强制使用）
      2. DashScope API（默认）
    """
    global _cached_embedder
    if _cached_embedder is not None:
        return _cached_embedder

    if force_local:
        _cached_embedder = LocalSentenceTransformerEmbedder()
        print(f"[Embedding] 使用本地模型: {_cached_embedder.model}")
        return _cached_embedder

    # 优先 DashScope API（无需本地 GPU）
    if config.dashscope.api_key:
        _cached_embedder = DashScopeEmbedder(
            api_key=config.dashscope.api_key,
            model=config.dashscope.embedding_model,
            api_url=config.dashscope.embedding_api_url,
        )
        print(f"[Embedding] 使用 DashScope API: {config.dashscope.embedding_model}")
        return _cached_embedder

    # 降级到本地模型
    try:
        _cached_embedder = LocalSentenceTransformerEmbedder()
        print(f"[Embedding] DashScope API 未配置，使用本地模型")
        return _cached_embedder
    except ImportError as e:
        raise RuntimeError(
            f"无法初始化 Embedding 模型：\n"
            f"  1. 配置 DASHSCOPE_API_KEY（推荐）\n"
            f"  2. 或安装 sentence-transformers：pip install sentence-transformers\n"
            f"  原始错误：{e}"
        )


def reset_embedder():
    """重置 embedder 缓存（重新加载配置时调用）"""
    global _cached_embedder
    if _cached_embedder:
        _cached_embedder.close()
    _cached_embedder = None
