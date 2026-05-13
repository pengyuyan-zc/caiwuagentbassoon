# -*- coding: utf-8 -*-
"""
知识库管理器

负责：
  1. 加载知识文档（Markdown / TXT）
  2. 文本分割（按 token 数或段落）
  3. 向量化并写入向量数据库
  4. 检索（向量搜索 + 可选重排序）
  5. 增量更新与索引重建
"""

from __future__ import annotations

import re
import hashlib
import json
import uuid
from pathlib import Path
from typing import Optional, Literal

from agent import config
from agent.knowledge.vector_store import VectorStore, ChromaStore, FaissStore, create_vector_store, Chunk
from agent.knowledge.embedding import get_embedding_model, DashScopeReranker, Embedder


# ══════════════════════════════════════════════════════════════════════════
# 文本分割策略
# ══════════════════════════════════════════════════════════════════════════

def split_text_by_tokens(text: str, max_tokens: int = 500, overlap: int = 50) -> list[str]:
    """
    简单分块策略：按固定 token 数切分（overlap 保持上下文连贯）。
    实际生产中可替换为 markdown 段落分割或语义分割。

    Args:
        text: 原始文本
        max_tokens: 每块最大 token 数（近似值）
        overlap: 块之间的重叠 token 数

    Returns:
        文本块列表
    """
    # 简单估算：1 token ≈ 1.5 个中文字符 或 4 个英文字符
    chars_per_token = 2.0
    chunk_chars = int(max_tokens * chars_per_token)

    chunks = []
    start = 0
    text_len = len(text)
    step = chunk_chars - overlap

    while start < text_len:
        end = min(start + chunk_chars, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
        if step <= 0:
            break

    return chunks


def split_markdown_by_sections(markdown_text: str, max_tokens: int = 500) -> list[tuple[str, str]]:
    """
    Markdown 文件分块策略：按 ## 标题分段。

    Returns:
        list of (section_title, section_content)
    """
    # 按 ## 或 ### 分割
    pattern = r'(^#{1,3}\s+.+?$)'
    parts = re.split(pattern, markdown_text, flags=re.MULTILINE)

    sections = []
    i = 0
    current_title = "文档开头"
    current_content_lines = []

    while i < len(parts):
        part = parts[i]
        if re.match(pattern, part):
            # 先保存之前的
            if current_content_lines:
                sections.append((current_title, "\n".join(current_content_lines)))
                current_content_lines = []
            current_title = part.strip()
        else:
            if part.strip():
                current_content_lines.append(part)
        i += 1

    if current_content_lines:
        sections.append((current_title, "\n".join(current_content_lines)))

    # 如果单节过长，继续拆分
    result = []
    for title, content in sections:
        if len(content) > max_tokens * 2:
            sub_chunks = split_text_by_tokens(content, max_tokens=max_tokens)
            for sc in sub_chunks:
                result.append((title, sc))
        else:
            result.append((title, content))

    return result


# ══════════════════════════════════════════════════════════════════════════
# 知识库管理器
# ══════════════════════════════════════════════════════════════════════════

class KnowledgeBaseManager:
    """
    知识库管理器

    使用流程：
        kb = KnowledgeBaseManager()
        kb.rebuild_index()          # 首次构建或重建索引
        results = kb.retrieve("发票如何入账？")   # 检索
    """

    def __init__(
        self,
        knowledge_dir: str = None,
        store: VectorStore = None,
        embedder: Embedder = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        top_k: int = 5,
    ):
        self.knowledge_dir = Path(knowledge_dir or config.rag.knowledge_dir)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k

        self.embedder = embedder or get_embedding_model()
        self.store = store or create_vector_store()

        # 加载 reranker（可选）
        self.reranker = None
        if config.rag.rerank_enabled:
            try:
                self.reranker = DashScopeReranker()
            except Exception as e:
                import sys
                sys.stderr.write(f"[KB] Reranker 初始化失败: {e}，跳过重排序\n")

    # ── 文档加载 ────────────────────────────────────────────────────────

    def _load_documents(self) -> list[tuple[Path, str]]:
        """加载知识目录下的所有文档"""
        docs = []
        if not self.knowledge_dir.exists():
            import sys
            sys.stderr.write(f"[KB] 知识目录不存在: {self.knowledge_dir}，跳过\n")
            return docs

        for ext in ("*.md", "*.txt", "*.markdown"):
            for file_path in self.knowledge_dir.glob(ext):
                try:
                    text = file_path.read_text(encoding="utf-8")
                    docs.append((file_path, text))
                except Exception as e:
                    import sys
                    sys.stderr.write(f"[KB] 读取文件失败 {file_path}: {e}\n")

        return docs

    def _chunk_document(self, file_path: Path, text: str) -> list[Chunk]:
        """将文档分割为 Chunk"""
        chunks = []
        file_stem = file_path.stem

        if file_path.suffix in (".md", ".markdown"):
            sections = split_markdown_by_sections(text, max_tokens=self.chunk_size)
            for i, (title, content) in enumerate(sections):
                if not content.strip():
                    continue
                chunk_id = f"{file_stem}_{i:04d}"
                chunk = Chunk(
                    id=chunk_id,
                    content=content.strip(),
                    metadata={
                        "source": str(file_path),
                        "title": title,
                        "category": file_path.stem,
                        "chunk_index": i,
                    }
                )
                chunks.append(chunk)
        else:
            raw_chunks = split_text_by_tokens(text, max_tokens=self.chunk_size, overlap=self.chunk_overlap)
            for i, content in enumerate(raw_chunks):
                if not content.strip():
                    continue
                chunk_id = f"{file_stem}_{i:04d}"
                chunk = Chunk(
                    id=chunk_id,
                    content=content.strip(),
                    metadata={
                        "source": str(file_path),
                        "category": file_stem,
                        "chunk_index": i,
                    }
                )
                chunks.append(chunk)

        return chunks

    # ── 索引构建 ────────────────────────────────────────────────────────

    def rebuild_index(self, force: bool = False) -> dict:
        """
        重建整个知识库索引。

        Args:
            force: 是否强制重建（否则增量更新）

        Returns:
            {"chunks_added": int, "files_processed": int, "error": str or None}
        """
        import sys
        sys.stderr.write(f"[KB] 开始构建索引，目录: {self.knowledge_dir}\n")

        docs = self._load_documents()
        if not docs:
            return {"chunks_added": 0, "files_processed": 0, "error": None}

        # 如果非强制且知识库已有数据，只处理新增/变更的文件
        if not force and self.store.count > 0:
            sys.stderr.write(f"[KB] 增量更新，当前向量数: {self.store.count}\n")
            return self._incremental_update(docs)

        # 全量重建
        all_chunks = []
        for file_path, text in docs:
            chunks = self._chunk_document(file_path, text)
            all_chunks.extend(chunks)

        if not all_chunks:
            return {"chunks_added": 0, "files_processed": len(docs), "error": "无有效内容"}

        # 向量化
        texts = [c.content for c in all_chunks]
        sys.stderr.write(f"[KB] 正在 embedding {len(texts)} 个文本块...\n")
        embeddings = self.embedder.embed(texts)

        # 写入向量数据库
        self.store.add_chunks(all_chunks, embeddings)
        self.store.save()

        sys.stderr.write(
            f"[KB] 索引构建完成！共 {len(all_chunks)} 个块，"
            f"来自 {len(docs)} 个文件，向量维度: {len(embeddings[0])}\n"
        )

        return {"chunks_added": len(all_chunks), "files_processed": len(docs), "error": None}

    def _incremental_update(self, docs: list[tuple[Path, str]]) -> dict:
        """增量更新：检查文件变化，只重建变更的文件"""
        import sys

        updated = 0
        for file_path, text in docs:
            # 用文件内容的 hash 判断是否变化（简化处理：实际可用 mtime）
            content_hash = hashlib.md5(text.encode()).hexdigest()
            metadata_hash_file = self.knowledge_dir / f".{file_path.stem}.hash"

            old_hash = ""
            if metadata_hash_file.exists():
                old_hash = metadata_hash_file.read_text().strip()

            if content_hash != old_hash:
                # 删除旧块，重新写入
                old_chunks = [f"{file_path.stem}_{i:04d}" for i in range(10000)]
                self.store.delete(old_chunks)
                new_chunks = self._chunk_document(file_path, text)
                if new_chunks:
                    texts = [c.content for c in new_chunks]
                    embeddings = self.embedder.embed(texts)
                    self.store.add_chunks(new_chunks, embeddings)
                    self.store.save()
                    metadata_hash_file.write_text(content_hash)
                    updated += 1
                sys.stderr.write(f"[KB] 更新文件: {file_path.name}\n")

        return {"chunks_added": self.store.count, "files_processed": len(docs), "updated_files": updated, "error": None}

    # ── 检索 ───────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = None, filter_metadata: dict = None) -> list[dict]:
        """
        检索最相关的知识片段。

        Args:
            query: 用户查询
            top_k: 返回条数（默认取配置值）
            filter_metadata: 按元数据过滤

        Returns:
            [{"content": str, "metadata": dict, "score": float}, ...]
        """
        top_k = top_k or self.top_k

        # 向量搜索
        chunks = self.store.search_by_text(
            query_text=query,
            embedder=self.embedder,
            top_k=top_k * 2 if self.reranker else top_k,  # reranker 需要更多候选
            filter_metadata=filter_metadata,
        )

        if not chunks:
            return []

        # 重排序（可选）
        if self.reranker and len(chunks) > top_k:
            candidate_texts = [c.content for c in chunks]
            reranked = self.reranker.rerank(query, candidate_texts, top_n=top_k)
            # 按重排序结果重新组织
            idx_map = {c.content: c for c in chunks}
            results = []
            for r in reranked:
                if r["text"] in idx_map:
                    chunk = idx_map[r["text"]]
                    results.append({
                        "content": chunk.content,
                        "metadata": chunk.metadata,
                        "score": r.get("score", 1.0 - r.get("index", 0) * 0.1),
                    })
            return results

        # 直接返回搜索结果
        return [
            {
                "content": c.content,
                "metadata": c.metadata,
                "score": 1.0 - c.metadata.get("_distance", 0.0) / 100.0,  # 归一化到 0~1
            }
            for c in chunks[:top_k]
        ]

    def retrieve_as_context(self, query: str, top_k: int = None) -> str:
        """
        将检索结果格式化为 LLM 上下文字符串。

        Returns:
            格式化后的字符串，可直接拼接到 system prompt
        """
        results = self.retrieve(query, top_k=top_k)
        if not results:
            return ""

        parts = ["【参考知识】"]
        for i, r in enumerate(results, 1):
            source = r["metadata"].get("source", "")
            title = r["metadata"].get("title", r["metadata"].get("category", ""))
            parts.append(f"\n--- 第 {i} 条 [{title}] ---\n{r['content']}")

        return "\n".join(parts)

    # ── 统计 ───────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """返回知识库统计信息"""
        return {
            "vector_count": self.store.count,
            "knowledge_dir": str(self.knowledge_dir),
            "embedder": type(self.embedder).__name__,
            "vector_store": type(self.store).__name__,
            "rerank_enabled": self.reranker is not None,
        }


# ══════════════════════════════════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════════════════════════════════

_kb_instance: Optional[KnowledgeBaseManager] = None


def get_kb_manager() -> KnowledgeBaseManager:
    """获取知识库管理器单例（延迟初始化）"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBaseManager()
    return _kb_instance


def reset_kb_manager():
    """重置知识库管理器（重新加载配置时调用）"""
    global _kb_instance
    _kb_instance = None
