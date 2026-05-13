# -*- coding: utf-8 -*-
"""
向量存储抽象层

支持多种向量数据库：
  - ChromaDB（开发/轻量推荐）
  - FAISS（单机高性能）

所有向量存储统一抽象为 VectorStore 接口，
可通过 config.rag.vector_store_type 切换。
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass, field

from agent import config


# ══════════════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Chunk:
    """文档块"""
    id: str
    content: str
    metadata: dict = field(default_factory=dict)
    # metadata 中可包含：source, page, chunk_index, category 等

    def to_dict(self) -> dict:
        return {"id": self.id, "content": self.content, "metadata": self.metadata}


# ══════════════════════════════════════════════════════════════════════════
# VectorStore 接口
# ══════════════════════════════════════════════════════════════════════════

class VectorStore:
    """向量存储抽象接口"""

    def __init__(self, persist_dir: str):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """
        添加文档块和对应向量。

        Args:
            chunks: 文档块列表
            embeddings: 向量列表（与 chunks 一一对应）
        """
        raise NotImplementedError

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filter_metadata: dict = None,
    ) -> list[Chunk]:
        """
        向量相似度搜索。

        Args:
            query_vector: 查询向量
            top_k: 返回前 top_k 条
            filter_metadata: 按 metadata 过滤（可选）

        Returns:
            按相似度降序排列的 Chunk 列表
        """
        raise NotImplementedError

    def search_by_text(
        self,
        query_text: str,
        embedder,
        top_k: int = 5,
        filter_metadata: dict = None,
    ) -> list[Chunk]:
        """先 embedding 再搜索（便捷封装）"""
        vector = embedder.embed_single(query_text)
        return self.search(vector, top_k=top_k, filter_metadata=filter_metadata)

    def save(self) -> None:
        """持久化到磁盘"""
        raise NotImplementedError

    def load(self) -> None:
        """从磁盘加载"""
        raise NotImplementedError

    def delete(self, chunk_ids: list[str]) -> None:
        """删除指定 ID 的块"""
        raise NotImplementedError

    @property
    def count(self) -> int:
        """返回向量总数"""
        raise NotImplementedError


# ══════════════════════════════════════════════════════════════════════════
# ChromaDB 实现
# ══════════════════════════════════════════════════════════════════════════

class ChromaStore(VectorStore):
    """
    ChromaDB 向量存储

    轻量、易用、支持元数据过滤。
    适合开发环境和小型知识库。
    """

    def __init__(self, persist_dir: str, collection_name: str = "finance_kb"):
        super().__init__(persist_dir)
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._init_client()

    def _init_client(self):
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise ImportError(
                "ChromaDB 未安装。\n"
                "  安装命令：pip install chromadb\n"
                "  或切换 FAISS 模式：VECTOR_STORE_TYPE=faiss"
            )

        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "财务智能体知识库"},
        )

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        ids = [c.id for c in chunks]
        contents = [c.content for c in chunks]
        metadatas = [c.metadata for c in chunks]

        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=contents,
            metadatas=metadatas,
        )
        self.save()

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filter_metadata: dict = None,
    ) -> list[Chunk]:
        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=filter_metadata,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        if results and results["ids"] and results["ids"][0]:
            for i, cid in enumerate(results["ids"][0]):
                dist = results["distances"][0][i] if "distances" in results else 0.0
                doc = results["documents"][0][i] if "documents" in results else ""
                meta = results["metadatas"][0][i] if "metadatas" in results else {}
                meta["_distance"] = dist
                chunks.append(Chunk(id=cid, content=doc, metadata=meta))

        return chunks

    def save(self) -> None:
        # ChromaDB PersistentClient 自动持久化，无需额外操作
        pass

    def load(self) -> None:
        # ChromaDB 启动时自动加载
        pass

    def delete(self, chunk_ids: list[str]) -> None:
        self._collection.delete(ids=chunk_ids)
        self.save()

    @property
    def count(self) -> int:
        return self._collection.count()


# ══════════════════════════════════════════════════════════════════════════
# FAISS 实现
# ══════════════════════════════════════════════════════════════════════════

class FaissStore(VectorStore):
    """
    FAISS 向量存储

    Facebook/Meta 高性能向量索引，适合大规模数据。
    需要配合其他元数据存储（SQLite）记录 chunk 信息。
    """

    def __init__(self, persist_dir: str, dimension: int = 1536):
        super().__init__(persist_dir)
        self.dimension = dimension
        self._index = None
        self._chunks: dict[str, Chunk] = {}
        self._id_to_idx: dict[str, int] = {}
        self._idx_to_id: dict[int, str] = {}
        self._init_index()
        self._load()

    def _init_index(self):
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "faiss 未安装。\n"
                "  安装命令：pip install faiss-cpu（或 faiss-gpu）\n"
                "  或切换 ChromaDB 模式：VECTOR_STORE_TYPE=chroma"
            )
        self._index = faiss.IndexFlatL2(self.dimension)

    def _load(self):
        index_file = self.persist_dir / "faiss.index"
        chunks_file = self.persist_dir / "chunks.pkl"
        if index_file.exists():
            import faiss
            self._index = faiss.read_index(str(index_file))
        if chunks_file.exists():
            with open(chunks_file, "rb") as f:
                data = pickle.load(f)
                self._chunks = data.get("chunks", {})
                self._id_to_idx = data.get("id_to_idx", {})
                self._idx_to_id = data.get("idx_to_id", {})

    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        import numpy as np
        if not chunks:
            return

        vectors = numpy.array(embeddings).astype("float32")
        self._index.add(vectors)

        for i, chunk in enumerate(chunks):
            idx = self._index.ntotal - len(chunks) + i
            self._chunks[chunk.id] = chunk
            self._id_to_idx[chunk.id] = idx
            self._idx_to_id[idx] = chunk.id

        self.save()

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filter_metadata: dict = None,
    ) -> list[Chunk]:
        import numpy as np
        q = numpy.array([query_vector]).astype("float32")
        distances, indices = self._index.search(q, min(top_k * 2, self._index.ntotal))

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx not in self._idx_to_id:
                continue
            chunk_id = self._idx_to_id[idx]
            chunk = self._chunks.get(chunk_id)
            if not chunk:
                continue
            if filter_metadata:
                skip = False
                for k, v in filter_metadata.items():
                    if chunk.metadata.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue
            chunk.metadata["_distance"] = float(dist)
            results.append(chunk)
            if len(results) >= top_k:
                break

        return results

    def save(self) -> None:
        import faiss
        faiss.write_index(self._index, str(self.persist_dir / "faiss.index"))
        with open(self.persist_dir / "chunks.pkl", "wb") as f:
            pickle.dump({
                "chunks": self._chunks,
                "id_to_idx": self._id_to_idx,
                "idx_to_id": self._idx_to_id,
            }, f)

    @property
    def count(self) -> int:
        return self._index.ntotal if self._index else 0


# ══════════════════════════════════════════════════════════════════════════
# 工厂函数
# ══════════════════════════════════════════════════════════════════════════

def create_vector_store(
    store_type: str = None,
    persist_dir: str = None,
    dimension: int = 1536,
) -> VectorStore:
    """
    根据配置创建向量存储实例。
    """
    store_type = store_type or config.rag.vector_store_type
    persist_dir = persist_dir or (
        config.rag.chroma_persist_dir if store_type == "chroma" else str(config.rag.knowledge_dir)
    )

    if store_type == "chroma":
        return ChromaStore(persist_dir)
    elif store_type == "faiss":
        return FaissStore(persist_dir, dimension=dimension)
    else:
        raise ValueError(f"不支持的向量存储类型: {store_type}，可选值：chroma / faiss")
