# -*- coding: utf-8 -*-
"""
财务智能体 - 统一配置管理

所有配置项从环境变量读取，提供类型安全的访问接口。
优先从 .env 文件加载，再从系统环境变量覆盖。
"""

from __future__ import annotations

import os
import json
import sqlite3
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass, field

# ══════════════════════════════════════════════════════════════════════════
# 路径配置
# ══════════════════════════════════════════════════════════════════════════

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()     # 财务智能体/
_AGENT_DIR = _PROJECT_ROOT / "agent"
_SKILLS_DIR = _AGENT_DIR / "skills"
_UPLOAD_DIR = _PROJECT_ROOT / "uploads"
_SESSIONS_DB = _PROJECT_ROOT / "sessions.db"

_UPLOAD_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════
# 加载 .env
# ══════════════════════════════════════════════════════════════════════════

def _load_env():
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

_load_env()

# ══════════════════════════════════════════════════════════════════════════
# 配置数据类
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class DashScopeConfig:
    api_key: str = field(default_factory=lambda: os.getenv("DASHSCOPE_API_KEY", ""))
    api_url: str = field(default_factory=lambda: os.getenv(
        "DASHSCOPE_API_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    ))
    embedding_api_url: str = field(default_factory=lambda: os.getenv(
        "DASHSCOPE_EMBEDDING_URL",
        "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    ))
    embedding_model: str = field(default_factory=lambda: os.getenv(
        "DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3"
    ))


@dataclass
class AgentConfig:
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "qwen-turbo"))
    max_loop: int = field(default_factory=lambda: int(os.getenv("MAX_LOOP", "15")))
    # 多节点工作流专用参数
    max_react_turns: int = field(default_factory=lambda: int(os.getenv("MAX_REACT_TURNS", "20")))
    # checkpoint 持久化策略
    checkpoint_persistence: Literal["memory", "sqlite", "postgres"] = field(
        default_factory=lambda: os.getenv("CHECKPOINT_PERSISTENCE", "memory")
    )
    sqlite_db_path: str = field(default_factory=lambda: os.getenv(
        "SQLITE_DB_PATH", str(_PROJECT_ROOT / "checkpoints.db")
    ))
    postgres_url: str = field(default_factory=lambda: os.getenv("POSTGRES_URL", ""))


@dataclass
class RAGConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("RAG_ENABLED", "false").lower() == "true")
    knowledge_dir: str = field(default_factory=lambda: os.getenv(
        "KNOWLEDGE_DIR", str(_AGENT_DIR / "knowledge" / "chunks")
    ))
    vector_store_type: Literal["chroma", "faiss"] = field(
        default_factory=lambda: os.getenv("VECTOR_STORE_TYPE", "chroma")
    )
    chroma_persist_dir: str = field(default_factory=lambda: os.getenv(
        "CHROMA_PERSIST_DIR", str(_AGENT_DIR / "knowledge" / "chroma_db")
    ))
    top_k: int = field(default_factory=lambda: int(os.getenv("RAG_TOP_K", "5")))
    rerank_enabled: bool = field(default_factory=lambda: os.getenv("RERANK_ENABLED", "false").lower() == "true")
    embedding_model: str = field(default_factory=lambda: os.getenv(
        "RAG_EMBEDDING_MODEL", "text-embedding-v3"
    ))
    embedding_api_key: str = field(default_factory=lambda: os.getenv(
        "DASHSCOPE_API_KEY", ""
    ))


@dataclass
class ServerConfig:
    host: str = field(default_factory=lambda: os.getenv("API_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "5001")))
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    # session 管理
    session_ttl_hours: int = field(default_factory=lambda: int(os.getenv("SESSION_TTL_HOURS", "168")))  # 7天


@dataclass
class HumanApprovalConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("HUMAN_APPROVAL_ENABLED", "false").lower() == "true")
    # 是否在凭证生成后强制人工确认
    force_for_vouchers: bool = field(default_factory=lambda: os.getenv(
        "HUMAN_APPROVAL_FOR_VOUCHERS", "false"
    ).lower() == "true")
    # 审批超时（秒），超时后自动取消
    timeout_seconds: int = field(default_factory=lambda: int(os.getenv("HUMAN_APPROVAL_TIMEOUT", "3600")))


# ══════════════════════════════════════════════════════════════════════════
# 全局配置单例
# ══════════════════════════════════════════════════════════════════════════

dashscope = DashScopeConfig()
agent = AgentConfig()
rag = RAGConfig()
server = ServerConfig()
human_approval = HumanApprovalConfig()


# ══════════════════════════════════════════════════════════════════════════
# Session 数据库（轻量 SQLite，不依赖 langgraph-checkpoint-sqlite）
# ══════════════════════════════════════════════════════════════════════════

def _init_sessions_db():
    """初始化 sessions 表"""
    conn = sqlite3.connect(str(_SESSIONS_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            metadata TEXT,  -- JSON 存储额外信息
            is_active INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,  -- JSON
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    """)
    conn.commit()
    conn.close()


_init_sessions_db()


def create_session(session_id: str, user_id: str = "default", metadata: dict = None) -> dict:
    """创建新会话"""
    import datetime
    now = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(str(_SESSIONS_DB))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, user_id, created_at, updated_at, metadata, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (session_id, user_id, now, now, json.dumps(metadata or {}))
        )
        conn.commit()
        return {"session_id": session_id, "user_id": user_id, "created_at": now, "updated_at": now}
    finally:
        conn.close()


def update_session(session_id: str, metadata: dict = None) -> None:
    """更新会话时间戳和元数据"""
    import datetime
    now = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(str(_SESSIONS_DB))
    try:
        if metadata:
            existing = get_session(session_id)
            if existing:
                old_meta = json.loads(existing.get("metadata") or "{}")
                old_meta.update(metadata)
                metadata = old_meta
        conn.execute(
            "UPDATE sessions SET updated_at = ?, metadata = ? WHERE session_id = ?",
            (now, json.dumps(metadata or {}), session_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_session(session_id: str) -> Optional[dict]:
    """获取会话信息"""
    conn = sqlite3.connect(str(_SESSIONS_DB))
    try:
        cur = conn.execute(
            "SELECT session_id, user_id, created_at, updated_at, metadata FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cur.fetchone()
        if row:
            return {
                "session_id": row[0], "user_id": row[1],
                "created_at": row[2], "updated_at": row[3],
                "metadata": row[4]
            }
        return None
    finally:
        conn.close()


def list_sessions(user_id: str = None, limit: int = 50) -> list[dict]:
    """列出用户的所有会话"""
    conn = sqlite3.connect(str(_SESSIONS_DB))
    try:
        if user_id:
            cur = conn.execute(
                "SELECT session_id, user_id, created_at, updated_at, metadata FROM sessions "
                "WHERE user_id = ? AND is_active = 1 ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit)
            )
        else:
            cur = conn.execute(
                "SELECT session_id, user_id, created_at, updated_at, metadata FROM sessions "
                "WHERE is_active = 1 ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            )
        return [
            {"session_id": r[0], "user_id": r[1], "created_at": r[2],
             "updated_at": r[3], "metadata": r[4]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """删除会话"""
    conn = sqlite3.connect(str(_SESSIONS_DB))
    try:
        cur = conn.execute("UPDATE sessions SET is_active = 0 WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def log_session_event(session_id: str, event_type: str, event_data: dict = None) -> None:
    """记录会话事件（用于 trace）"""
    import datetime
    now = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(str(_SESSIONS_DB))
    try:
        conn.execute(
            "INSERT INTO session_events (session_id, event_type, event_data, created_at) VALUES (?, ?, ?, ?)",
            (session_id, event_type, json.dumps(event_data or {}), now)
        )
        conn.commit()
    finally:
        conn.close()


def get_session_trace(session_id: str, limit: int = 100) -> list[dict]:
    """获取会话的执行轨迹"""
    conn = sqlite3.connect(str(_SESSIONS_DB))
    try:
        cur = conn.execute(
            "SELECT id, event_type, event_data, created_at FROM session_events "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit)
        )
        return [
            {"id": r[0], "event_type": r[1], "event_data": r[2], "created_at": r[3]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
# 配置验证
# ══════════════════════════════════════════════════════════════════════════

def validate_config(strict: bool = False) -> list[dict]:
    """
    验证必需配置项是否已设置。

    Args:
        strict: 是否严格模式（严格模式下缺少必需配置会抛异常）

    Returns:
        验证结果列表，每项包含 {"name": str, "valid": bool, "message": str}

    Raises:
        MissingConfigError: strict=True 且缺少必需配置时
    """
    from agent.errors import MissingConfigError

    results = []

    # ── 必需配置 ──────────────────────────────────────────────────────
    required_configs = [
        ("DASHSCOPE_API_KEY", dashscope.api_key, "DashScope API Key"),
        ("API_HOST", server.host, "服务主机地址"),
        ("API_PORT", server.port, "服务端口"),
    ]

    for env_var, value, name in required_configs:
        valid = bool(value) and value not in ("", "sk-your-key-here", "sk-xxx")
        message = "已设置" if valid else f"未设置或使用默认值，请在 .env 中配置 {env_var}"
        results.append({
            "name": name,
            "env_var": env_var,
            "valid": valid,
            "message": message,
            "required": True,
        })
        if strict and not valid:
            raise MissingConfigError(name, env_var)

    # ── 可选配置（警告但不报错）───────────────────────────────────────
    optional_configs = [
        ("LLM_MODEL", agent.model, "LLM 模型"),
        ("MAX_LOOP", agent.max_loop, "最大循环次数"),
        ("RAG_ENABLED", rag.enabled, "RAG 知识库"),
    ]

    for env_var, value, name in optional_configs:
        results.append({
            "name": name,
            "env_var": env_var,
            "valid": True,  # 可选配置始终视为有效
            "message": f"当前值: {value}",
            "required": False,
        })

    return results


def check_startup_config() -> None:
    """
    启动时检查配置，打印配置状态。

    如果缺少必需配置，打印警告信息。
    """
    print("=" * 60)
    print("  配置检查")
    print("=" * 60)

    results = validate_config(strict=False)

    for r in results:
        status = "✓" if r["valid"] else "⚠"
        req = "[必需]" if r["required"] else "[可选]"
        print(f"  {status} {req} {r['name']}: {r['message']}")

    # 检查是否有必需配置缺失
    missing = [r for r in results if not r["valid"] and r["required"]]
    if missing:
        print("")
        print("  ⚠ 警告：以下必需配置未设置，服务可能无法正常运行：")
        for r in missing:
            print(f"    - {r['name']}: 请在 .env 文件中设置 {r['env_var']}")
        print("")
        print("  .env 文件示例：")
        print("    DASHSCOPE_API_KEY=sk-your-actual-api-key")
        print("    LLM_MODEL=qwen-turbo")
        print("=" * 60)
    else:
        print("=" * 60)
