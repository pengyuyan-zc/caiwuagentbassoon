# API 接口文档

财务智能体 FastAPI 服务接口说明（v2.1）

## 基础信息

- **服务地址**: `http://127.0.0.1:5001`（可通过 `API_HOST` 和 `API_PORT` 配置）
- **API 文档**: `http://127.0.0.1:5001/docs`（Swagger UI）
- **交互式文档**: `http://127.0.0.1:5001/redoc`

## 响应格式

### 成功响应

```json
{
  "success": true,
  "data": { ... }
}
```

### 错误响应

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "用户友好的错误消息",
    "details": { ... }
  }
}
```

---

## 接口列表

### 健康检查

#### GET `/health`

返回服务状态和已加载的 Skills。

**响应示例**:

```json
{
  "status": "ok",
  "service": "财务智能体 - LangGraph v2 多节点工作流",
  "model": "qwen-turbo",
  "langgraph": true,
  "skills": [
    {"name": "invoice-tax-voucher", "description": "生成开票税务凭证", "path": "..."}
  ],
  "checkpoint_persistence": "memory",
  "human_approval_enabled": false
}
```

---

### Skills 接口

#### GET `/api/agent/skills`

列出所有可用的 Skills 工具。

**响应示例**:

```json
{
  "skills": [
    {
      "name": "invoice-tax-voucher",
      "description": "生成开票税务凭证",
      "path": "F:\\...\\skills\\invoice-tax-voucher"
    }
  ]
}
```

---

### 对话接口

#### POST `/api/agent/chat`

发送消息并获取回复（支持文件上传）。

**请求参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 用户消息 |
| `session_id` | string | 否 | 会话 ID（用于会话隔离） |
| `files` | file[] | 否 | 上传的 Excel 文件 |

**响应示例**:

```json
{
  "reply": "凭证生成完成！\n• 凭证数量：15 张\n• 分录数量：45 条",
  "session_id": "sess_xxx",
  "tools_used": ["invoke_invoice_voucher"],
  "download_url": "http://127.0.0.1:5001/download?file=..."
}
```

#### POST `/api/agent/chat/stream`

流式对话接口（SSE 格式）。

**事件类型**:

| 事件 | 说明 |
|------|------|
| `content` | AI 回复内容片段 |
| `tools` | 使用的工具列表 |
| `approval` | 进入人工审批 |
| `done` | 完成（包含完整数据） |
| `error` | 错误信息 |

**示例事件流**:

```
event: tools
data: {"tools": ["invoke_invoice_voucher"]}

event: content
data: {"content": "凭证生成完成"}

event: done
data: {"reply": "...", "download_url": "...", "session_id": "..."}
```

---

### 审批接口

#### POST `/api/agent/approve`

人工审批确认/拒绝。

**请求参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `session_id` | string | 是 | 待审批的会话 ID |
| `action` | string | 是 | 动作：`approve`/`reject`/`modify` |
| `modifications` | string | 否 | 修改参数（JSON 字符串，action=modify 时） |

**响应示例**:

```json
{
  "success": true,
  "message": "凭证生成完成",
  "resumed": true
}
```

#### GET `/api/agent/state/{session_id}`

获取会话的当前状态快照。

**响应示例**:

```json
{
  "session_id": "sess_xxx",
  "step": 3,
  "finished": false,
  "waiting_for_approval": true,
  "approval_data": {
    "voucher_count": 15,
    "line_count": 45
  },
  "current_node": "human_approval",
  "node_path": ["model", "tools", "model"]
}
```

---

### Session 管理接口

#### GET `/api/sessions`

列出所有会话。

**查询参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `user_id` | string | 按用户过滤 |
| `limit` | int | 返回数量限制（默认 50） |

#### POST `/api/sessions`

创建新会话。

**请求参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `user_id` | string | 否 | 用户 ID（默认 `default`） |
| `metadata` | string | 否 | 元数据（JSON 字符串） |

#### GET `/api/sessions/{session_id}`

获取指定会话信息。

#### DELETE `/api/sessions/{session_id}`

删除会话。

#### PATCH `/api/sessions/{session_id}`

更新会话元数据。

#### GET `/api/sessions/{session_id}/trace`

获取会话的执行轨迹。

---

### 文件下载

#### GET `/download?file={path}`

下载生成的文件。

---

### RAG 知识库接口

#### POST `/api/knowledge/rebuild`

重建知识库索引。

#### GET `/api/knowledge/stats`

获取知识库统计信息。

#### GET `/api/knowledge/search?q={query}`

测试知识库检索。

---

## 错误码对照表

| 错误码 | 说明 | HTTP 状态码 |
|--------|------|-------------|
| `FILE_NOT_FOUND` | 文件不存在 | 404 |
| `FILE_FORMAT_ERROR` | 文件格式不正确 | 400 |
| `SKILL_NOT_FOUND` | Skill 不存在 | 404 |
| `MISSING_PARAMETER` | 缺少必需参数 | 400 |
| `SESSION_NOT_FOUND` | 会话不存在 | 404 |
| `SESSION_EXPIRED` | 会话已过期 | 404 |
| `LLM_CONNECTION_ERROR` | AI 服务连接失败 | 503 |
| `LLM_TIMEOUT_ERROR` | AI 服务超时 | 503 |
| `LLM_RATE_LIMIT_ERROR` | 请求频率超限 | 429 |
| `VALIDATION_ERROR` | 参数验证失败 | 422 |
| `MISSING_CONFIG` | 缺少必需配置 | 500 |
| `INTERNAL_ERROR` | 内部错误 | 500 |