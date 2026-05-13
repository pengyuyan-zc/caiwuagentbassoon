# -*- coding: utf-8 -*-
"""
FastAPI 后端服务 - 财务智能体 LangGraph Agent API（v2）

启动方式：
    python -m agent.server
    或
    uvicorn agent.server:app --reload --port 5001

v2 新增功能：
    - 多会话管理（session_id 隔离）
    - checkpoint 持久化（SQLite / Memory）
    - 人工审批 API（/api/agent/approve, /api/agent/reject）
    - session 管理 API（/api/sessions）
    - 审批预览数据（从 agent state 提取）
    - 真正的节点级流式输出（stream_events）
    - 结构化错误处理（统一错误码）
"""

from __future__ import annotations

import asyncio
import functools
import json
import time
import uuid
import urllib.parse
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from pydantic import field_validator

# ── 路径设置 ──────────────────────────────────────────────────────────────

_CURRENT_DIR = Path(__file__).resolve().parent           # agent/
_PROJECT_ROOT = _CURRENT_DIR.parent                        # 财务智能体/
_SKILLS_DIR = _CURRENT_DIR / "skills"            # skills/
_UPLOAD_DIR = _PROJECT_ROOT / "uploads"
_UPLOAD_DIR.mkdir(exist_ok=True)

# ── 导入配置模块 ──────────────────────────────────────────────────────────
from agent import config as _cfg

# ── Python 3.7+ 兼容：替代 asyncio.to_thread ──────────────────────────────
async def run_sync(func, *args, **kwargs):
    """
    在异步上下文中运行同步函数（兼容 Python 3.7+）

    Python 3.9+ 可以直接使用 asyncio.to_thread，但为了兼容低版本，
    使用 run_in_executor 包装。
    """
    loop = asyncio.get_event_loop()
    if kwargs:
        func = functools.partial(func, **kwargs)
    return await loop.run_in_executor(None, func, *args)

# ── 延迟导入（避免顶层循环依赖） ──────────────────────────────────────────

def _get_agent_v1():
    from agent.finance_agent import create_react_agent
    return create_react_agent(use_v2=False)


def _get_agent_v2():
    from agent.finance_agent import create_react_agent
    return create_react_agent(use_v2=True)


def _get_agent():
    return _get_agent_v2()  # 默认使用 v2


# ── FastAPI 应用 ─────────────────────────────────────────────────────────

app = FastAPI(
    title="财务智能体 API",
    description="基于 LangGraph ReAct Agent 的智能财务助手（v2 多节点工作流，结构化错误处理）",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册异常处理器 ──────────────────────────────────────────────────────
from agent.middleware.error_handler import register_exception_handlers
register_exception_handlers(app)

# ── 请求/响应模型 ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话 ID（用于会话隔离）")
    model: Optional[str] = Field(None, description="模型名称")


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    tools_used: List[str] = Field(default_factory=list)
    download_url: Optional[str] = None
    details: Optional[str] = None


class ApprovalRequest(BaseModel):
    session_id: str = Field(..., description="待审批的会话 ID")
    action: str = Field(..., description="审批动作：approve（确认）/ reject（拒绝）/ modify（修改后重试）")
    modifications: Optional[dict] = Field(None, description="修改参数（当 action=modify 时）")


class ApprovalResponse(BaseModel):
    success: bool
    message: str
    resumed: bool


class SessionInfo(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    created_at: str
    updated_at: str
    metadata: Optional[dict] = None


class SkillInfo(BaseModel):
    name: str
    description: str
    path: str


class HealthResponse(BaseModel):
    status: str
    service: str
    model: str
    langgraph: bool
    skills: List[SkillInfo]


# ── 辅助函数 ─────────────────────────────────────────────────────────────

def _save_upload_file(uploaded_file: UploadFile) -> Path:
    """保存上传文件"""
    safe_name = f"upload_{int(time.time())}_{uuid.uuid4().hex[:8]}_{uploaded_file.filename}"
    file_path = _UPLOAD_DIR / safe_name
    content = uploaded_file.file.read()
    with open(str(file_path), "wb") as f:
        f.write(content)
    return file_path


def _get_or_create_session(session_id: Optional[str], user_id: str = "default") -> str:
    """获取或创建 session"""
    from agent import config as _cfg
    if session_id:
        existing = _cfg.get_session(session_id)
        if existing:
            _cfg.update_session(session_id)
            return session_id
    # 创建新 session
    new_id = session_id or str(uuid.uuid4())
    _cfg.create_session(new_id, user_id)
    return new_id


def _extract_final_reply(messages: List[dict]) -> str:
    """从消息列表中提取最终回复"""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            return msg["content"]
    return "处理完成，无返回内容"


def _get_used_tools(messages: List[dict]) -> List[str]:
    """从消息中提取使用的工具列表"""
    tools = []
    for msg in messages:
        if "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                tools.append(tc["function"]["name"])
    return list(dict.fromkeys(tools))


def _build_reply_and_url(messages: List[dict]) -> tuple[str, Optional[str]]:
    """
    从 tool 消息中提取凭证结果，构建 reply 和 download_url。
    兼容两套字段名：
      - 工资类凭证：approval_count / entry_count
      - 开票类凭证：voucher_count / line_count
    """
    # 找最后一个成功的凭证生成结果
    voucher_result = None
    for msg in reversed(messages):
        if msg.get("role") == "tool":
            try:
                content = msg.get("content", "")
                parsed = json.loads(content)
                if isinstance(parsed, dict) and parsed.get("output_file"):
                    voucher_result = parsed
                    break
            except Exception:
                pass

    if not voucher_result:
        return "", None

    if voucher_result.get("success") is False:
        return voucher_result.get("message", "操作失败"), None

    safe_path = voucher_result["output_file"].replace("\\", "/")
    encoded_path = urllib.parse.quote(safe_path)
    port = _cfg.server.port
    download_url = f"http://127.0.0.1:{port}/download?file={encoded_path}"

    # 兼容两套字段名
    voucher_count = voucher_result.get("voucher_count") or voucher_result.get("approval_count") or 0
    line_count = voucher_result.get("line_count") or voucher_result.get("entry_count") or 0

    reply = (
        f"凭证生成完成！\n"
        f"• 凭证数量：{voucher_count} 张\n"
        f"• 分录数量：{line_count} 条\n\n"
        f"[点击下载凭证文件]({download_url})"
    )
    return reply, download_url


# ── API 路由 ─────────────────────────────────────────────────────────────

@app.get("/", tags=["root"])
async def root():
    return {"message": "财务智能体 API v2", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse, tags=["健康检查"])
async def health():
    from agent.finance_agent import is_langgraph_available, list_skills, DEFAULT_MODEL
    from agent import config as _cfg
    return HealthResponse(
        status="ok",
        service="财务智能体 - LangGraph v2 多节点工作流",
        model=DEFAULT_MODEL,
        langgraph=is_langgraph_available(),
        skills=[SkillInfo(**s) for s in list_skills()],
        checkpoint_persistence=_cfg.agent.checkpoint_persistence,
        human_approval_enabled=_cfg.human_approval.enabled,
    )


# ── Skills ───────────────────────────────────────────────────────────────

@app.get("/api/agent/skills", tags=["Agent"])
async def list_skills_api():
    """列出所有可用 Skills"""
    from agent.finance_agent import list_skills as _list_skills
    return {"skills": _list_skills()}


# ── 核心对话接口 ─────────────────────────────────────────────────────────

@app.post("/api/agent/chat", response_model=ChatResponse, tags=["Agent"])
async def chat(
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    session_id: Optional[str] = Form(None),
):
    """
    Agent 对话接口（支持上传文件 + 多会话隔离）。
    """
    # 文件处理
    file_paths = []
    for f in files:
        if f and f.filename:
            file_paths.append(_save_upload_file(f))

    if file_paths:
        file_list_str = "\n".join(f"上传文件路径：{p}" for p in file_paths)
        message = f"{message}\n\n{file_list_str}"

    # session 管理
    sid = _get_or_create_session(session_id)
    from agent import config as _cfg
    _cfg.log_session_event(sid, "chat_start", {"message": message[:100], "file_count": len(file_paths)})

    try:
        agent = _get_agent()
        config = {
            "configurable": {
                "thread_id": sid,
                "checkpoint_ns": f"user_default",
            }
        }
        input_state = {
            "messages": [{"role": "user", "content": message}],
            #"tool_results": [],
            #"step": 0,
            "finished": False,
            "waiting_for_approval": False,
            "approval_data": None,
            "approval_action": None,
            "approval_modifications": None,
            "last_assistant_msg": None,
            "node_path": [],
            "current_node": None,
        }
        result = await run_sync(agent.invoke, input_state, config=config)

        messages = result.get("messages", [])
        tools_used = _get_used_tools(messages)

        final_reply, download_url = _build_reply_and_url(messages)
        if not final_reply:
            final_reply = _extract_final_reply(messages)

        # 如果有文件但 LLM 未调用工具，兜底直接调用
        if file_paths and not tools_used:
            from agent.finance_agent import invoke_skill as _invoke_skill
            skill_res = _invoke_skill("invoice-tax-voucher", input_files=[str(p) for p in file_paths])
            if skill_res.get("success") and skill_res.get("output_file"):
                safe_path = skill_res["output_file"].replace("\\", "/")
                encoded_path = urllib.parse.quote(safe_path)
                download_url = f"http://127.0.0.1:{_cfg.server.port}/download?file={encoded_path}"
        # 兜底：兼容两套字段名
        skill_voucher = skill_res.get("voucher_count") or skill_res.get("approval_count") or 0
        skill_line = skill_res.get("line_count") or skill_res.get("entry_count") or 0
        final_reply = (
            f"已根据上传的文件自动生成凭证（共 {len(file_paths)} 个文件）：\n"
            f"• 凭证数量：{skill_voucher} 张\n"
            f"• 分录数量：{skill_line} 条\n\n"
            f"[点击下载凭证文件]({download_url})"
        )

        _cfg.log_session_event(sid, "chat_end", {"tools_used": tools_used})
        _cfg.update_session(sid, {"last_reply": final_reply[:200]})

        return ChatResponse(
            reply=final_reply,
            session_id=sid,
            tools_used=tools_used,
            download_url=download_url,
        )

    except Exception as e:
        import traceback
        _cfg.log_session_event(sid, "chat_error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"{e}\n{traceback.format_exc()}")


# ── 流式对话接口 ─────────────────────────────────────────────────────────

@app.post("/api/agent/chat/stream", tags=["Agent"])
async def chat_stream(
    message: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    session_id: Optional[str] = Form(None),
):
    """
    流式输出接口：
    - event: tools —— 使用了哪些工具
    - event: approval —— 进入人工审批，等待确认
    - event: content —— 回复内容片段
    - event: done —— 完成（包含完整数据）
    - event: error —— 错误
    """
    file_paths = []
    for f in files:
        if f and f.filename:
            file_paths.append(_save_upload_file(f))

    if file_paths:
        file_list_str = "\n".join(f"上传文件路径：{p}" for p in file_paths)
        message = f"{message}\n\n{file_list_str}"

    sid = _get_or_create_session(session_id)
    from agent import config as _cfg
    _cfg.log_session_event(sid, "stream_start", {"message": message[:100]})

    async def generate():
        import sys as _sys_err
        _sys_err.stderr.write(f"[stream] 请求开始，session={sid}\n")
        _sys_err.stderr.flush()
        try:
            import io, sys as _sys
            _old_stdout = _sys.stdout
            _old_stderr = _sys.stderr

            _null_buffer = io.BytesIO()
            _sys.stdout = io.TextIOWrapper(_null_buffer, encoding="utf-8", line_buffering=True)
            _sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", line_buffering=True)

            try:
                agent = _get_agent()
                config = {
                    "configurable": {
                        "thread_id": sid,
                        "checkpoint_ns": f"user_default",
                    }
                }
                input_state = {
                    "messages": [{"role": "user", "content": message}],
                    #"tool_results": [],
                    #"step": 0,
                    "finished": False,
                    "waiting_for_approval": False,
                    "approval_data": None,
                    "approval_action": None,
                    "approval_modifications": None,
                    "last_assistant_msg": None,
                    "node_path": [],
                    "current_node": None,
                }

                # 尝试使用 stream_events 真正流式输出
                try:
                    # 尝试节点级流式
                    for event in agent.stream_events(input_state, config, stream_mode="values"):
                        event_type = event.get("type", "")
                        data = event.get("data", {})
                        if event_type == "values":
                            current_node = data.get("current_node", "")
                            waiting = data.get("waiting_for_approval", False)
                            if waiting:
                                approval_data = data.get("approval_data", {})
                                yield f"event: approval\ndata: {json.dumps(approval_data, ensure_ascii=False)}\n\n"
                            # 提取消息增量
                            msgs = data.get("messages", [])
                            if msgs:
                                last = msgs[-1]
                                if last.get("role") == "assistant" and last.get("content"):
                                    content = last["content"]
                                    if len(content) > 0:
                                        yield f"event: content\ndata: {json.dumps({'content': content[-50:], 'node': current_node}, ensure_ascii=False)}\n\n"
                except Exception as _stream_err:
                    _sys_err.stderr.write(f"[stream] stream_events 不支持，降级为普通调用: {_stream_err}\n")
                    _sys_err.stderr.flush()
                    # 降级：普通调用
                    result = await run_sync(agent.invoke, input_state, config=config)
            finally:
                _sys.stdout = _old_stdout
                _sys.stderr = _old_stderr

            messages = result.get("messages", [])
            tools_used = _get_used_tools(messages)
            final_reply, download_url = _build_reply_and_url(messages)
            if not final_reply:
                final_reply = _extract_final_reply(messages)

            # 兜底工具调用
            if file_paths and not tools_used:
                from agent.finance_agent import invoke_skill as _invoke_skill
                skill_res = _invoke_skill("invoice-tax-voucher", input_files=[str(p) for p in file_paths])
                if skill_res.get("success") and skill_res.get("output_file"):
                    safe_path = skill_res["output_file"].replace("\\", "/")
                    encoded_path = urllib.parse.quote(safe_path)
                    download_url = f"http://127.0.0.1:{_cfg.server.port}/download?file={encoded_path}"
                    # 兜底：兼容两套字段名
                    skill_voucher = skill_res.get("voucher_count") or skill_res.get("approval_count") or 0
                    skill_line = skill_res.get("line_count") or skill_res.get("entry_count") or 0
                    final_reply = (
                        f"已根据上传的文件自动生成凭证（共 {len(file_paths)} 个文件）：\n"
                        f"• 凭证数量：{skill_voucher} 张\n"
                        f"• 分录数量：{skill_line} 条\n\n"
                        f"[点击下载凭证文件]({download_url})"
                    )

            _sys_err.stderr.write(f"[stream] 完成，tools={tools_used}, reply_len={len(final_reply)}\n")

            if tools_used:
                yield f"event: tools\ndata: {json.dumps(tools_used)}\n\n"

            chunk_size = 20
            for i in range(0, len(final_reply), chunk_size):
                chunk = final_reply[i:i + chunk_size]
                yield f"event: content\ndata: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

            yield f"event: done\ndata: {json.dumps({'reply': final_reply, 'tools': tools_used, 'download_url': download_url, 'session_id': sid}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            _sys_err.stderr.write(f"[stream] 异常: {e}\n{traceback.format_exc()}\n")
            _sys_err.stderr.flush()
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ── 人工审批接口 ─────────────────────────────────────────────────────────

@app.post("/api/agent/approve", response_model=ApprovalResponse, tags=["人工审批"])
async def approve(
    session_id: str = Form(...),
    action: str = Form(...),
    modifications: Optional[str] = Form(None),
):
    """
    人工审批接口。
    action: approve（确认）/ reject（拒绝）/ modify（修改后重试）
    """
    from agent import config as _cfg

    if action not in ("approve", "reject", "modify"):
        raise HTTPException(status_code=400, detail="action 必须为 approve / reject / modify")

    if action == "modify" and not modifications:
        raise HTTPException(status_code=400, detail="action=modify 时必须提供 modifications 参数")

    modifications_data = None
    if modifications:
        try:
            modifications_data = json.loads(modifications)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="modifications 必须为有效的 JSON")

    # 获取 agent 并 resume
    try:
        agent = _get_agent()
        resume_config = {
            "configurable": {
                "thread_id": session_id,
                "checkpoint_ns": "user_default",
            }
        }
        # 注入审批结果到 state
        resume_input = Command(
            resume={
                "approval_action": action,
                "approval_modifications": modifications_data,
                "waiting_for_approval": False,
            }
        )

        result = await run_sync(
            agent.invoke, resume_input, config=resume_config
        )

        messages = result.get("messages", [])
        final_reply, download_url = _build_reply_and_url(messages)
        if not final_reply:
            final_reply = _extract_final_reply(messages)

        _cfg.log_session_event(session_id, "approval", {"action": action, "modifications": modifications_data})
        _cfg.update_session(session_id)

        return ApprovalResponse(
            success=True,
            message=final_reply,
            resumed=True,
        )
    except Exception as e:
        import traceback
        return ApprovalResponse(
            success=False,
            message=f"恢复执行失败: {e}",
            resumed=False,
        )


@app.get("/api/agent/state/{session_id}", tags=["Agent"])
async def get_agent_state(session_id: str):
    """
    获取指定会话的当前状态快照（包含 approval_data 等中间状态）。
    """
    from agent import config as _cfg

    session = _cfg.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")

    try:
        agent = _get_agent()
        state = agent.get_state({
            "configurable": {
                "thread_id": session_id,
                "checkpoint_ns": "user_default",
            }
        })
        if not state:
            raise HTTPException(status_code=404, detail="无法获取状态（会话可能已过期）")

        # 提取关键字段
        values = state.values if hasattr(state, "values") else {}
        return {
            "session_id": session_id,
            "step": values.get("step", 0),
            "finished": values.get("finished", False),
            "waiting_for_approval": values.get("waiting_for_approval", False),
            "approval_data": values.get("approval_data"),
            "current_node": values.get("current_node"),
            "node_path": values.get("node_path", []),
            "tool_results_count": len(values.get("tool_results", [])),
            "messages_count": len(values.get("messages", [])),
            "next_node": state.next if hasattr(state, "next") else None,
        }
    except Exception as e:
        return {
            "session_id": session_id,
            "error": str(e),
        }


# ── Session 管理 ─────────────────────────────────────────────────────────

@app.get("/api/sessions", tags=["Session"])
async def list_sessions(user_id: Optional[str] = None, limit: int = 50):
    """列出所有会话"""
    from agent import config as _cfg
    sessions = _cfg.list_sessions(user_id=user_id, limit=limit)
    return {"sessions": sessions, "total": len(sessions)}


@app.post("/api/sessions", tags=["Session"])
async def create_session(user_id: str = Form("default"), metadata: str = Form("{}")):
    """创建新会话"""
    from agent import config as _cfg
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        meta = {}
    sid = str(uuid.uuid4())
    _cfg.create_session(sid, user_id, meta)
    return {"session_id": sid, "created": True}


@app.get("/api/sessions/{session_id}", tags=["Session"])
async def get_session(session_id: str):
    """获取指定会话信息"""
    from agent import config as _cfg
    session = _cfg.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return session


@app.delete("/api/sessions/{session_id}", tags=["Session"])
async def delete_session(session_id: str):
    """删除会话"""
    from agent import config as _cfg
    deleted = _cfg.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return {"deleted": True, "session_id": session_id}


@app.patch("/api/sessions/{session_id}", tags=["Session"])
async def update_session(session_id: str, metadata: str = Form(None)):
    """更新会话元数据（如保存消息历史）"""
    from agent import config as _cfg
    session = _cfg.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    meta = {}
    if metadata:
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="metadata 必须为有效 JSON")
    _cfg.update_session(session_id, meta)
    return {"updated": True, "session_id": session_id}


@app.get("/api/sessions/{session_id}/trace", tags=["Session"])
async def get_session_trace(session_id: str, limit: int = 100):
    """获取会话的执行轨迹"""
    from agent import config as _cfg
    session = _cfg.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    trace = _cfg.get_session_trace(session_id, limit=limit)
    return {"session_id": session_id, "events": trace, "total": len(trace)}


# ── 文件下载 ─────────────────────────────────────────────────────────────

@app.get("/download", tags=["文件"])
async def download(file: str = ""):
    """文件下载"""
    file_path = Path(urllib.parse.unquote(file))
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file}")
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── RAG 知识库 API ─────────────────────────────────────────────────────────

@app.post("/api/knowledge/rebuild", tags=["RAG"])
async def rebuild_knowledge_base(force: bool = Form(False)):
    """重建知识库索引"""
    from agent import config as _cfg
    if not _cfg.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG 未启用，请设置 RAG_ENABLED=true")
    try:
        from agent.knowledge.kb_manager import get_kb_manager, reset_kb_manager
        reset_kb_manager()
        kb = get_kb_manager()
        result = kb.rebuild_index(force=force)
        stats = kb.stats
        return {
            "success": True,
            "chunks_added": result.get("chunks_added", 0),
            "files_processed": result.get("files_processed", 0),
            "stats": stats,
        }
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"索引重建失败: {e}\n{traceback.format_exc()}")


@app.get("/api/knowledge/stats", tags=["RAG"])
async def knowledge_stats():
    """获取知识库统计信息"""
    from agent import config as _cfg
    if not _cfg.rag.enabled:
        return {"enabled": False, "message": "RAG 未启用"}
    try:
        from agent.knowledge.kb_manager import get_kb_manager
        kb = get_kb_manager()
        return {"enabled": True, "stats": kb.stats}
    except Exception as e:
        return {"enabled": True, "error": str(e), "stats": {}}


@app.get("/api/knowledge/search", tags=["RAG"])
async def knowledge_search(q: str = "", top_k: int = 5):
    """测试知识库检索"""
    from agent import config as _cfg
    if not _cfg.rag.enabled:
        raise HTTPException(status_code=400, detail="RAG 未启用")
    if not q:
        raise HTTPException(status_code=400, detail="请提供查询参数 q")
    try:
        from agent.knowledge.kb_manager import get_kb_manager
        kb = get_kb_manager()
        results = kb.retrieve(q, top_k=top_k)
        return {"query": q, "results": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 启动服务 ─────────────────────────────────────────────────────────────

def run_server(
    host: str = None,
    port: int = None,
    model: Optional[str] = None,
    use_v2: bool = True,
    check_config: bool = True,
):
    """
    启动 FastAPI 服务

    Args:
        host: 服务主机地址，默认从 config.server.host 读取
        port: 服务端口，默认从 config.server.port 读取
        model: LLM 模型名称，默认从 config.agent.model 读取
        use_v2: 是否使用 v2 多节点工作流
        check_config: 是否在启动时检查配置
    """
    import uvicorn
    from agent.finance_agent import is_langgraph_available, list_skills, DEFAULT_MODEL

    # 从 config 获取默认值
    host = host or _cfg.server.host
    port = port or _cfg.server.port
    model = model or DEFAULT_MODEL

    # 配置检查
    if check_config:
        _cfg.check_startup_config()

    print("=" * 60)
    print("  财务智能体 - FastAPI 服务 v2.1")
    print("=" * 60)
    print(f"  访问地址：http://{host}:{port}")
    print(f"  API 文档  ：http://{host}:{port}/docs")
    print(f"  模型      : {model}")
    print(f"  LangGraph : {'已安装（v2 多节点）' if is_langgraph_available() else '未安装，使用纯 Python ReAct'}")
    print(f"  Checkpoint: {_cfg.agent.checkpoint_persistence} ({_cfg.agent.sqlite_db_path if _cfg.agent.checkpoint_persistence == 'sqlite' else 'memory'})")
    print(f"  人工审批  : {'已启用' if _cfg.human_approval.enabled else '未启用'}")
    print(f"  RAG       : {'已启用' if _cfg.rag.enabled else '未启用'}")
    print("  Skills    :")
    for s in list_skills():
        print(f"    - {s['name']}  {s['description'] or ''}")
    print("=" * 60)

    uvicorn.run(
        "agent.server:app",
        host=host,
        port=port,
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    run_server()
