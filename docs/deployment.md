# 部署文档

本文档说明财务智能体的部署方式和生产环境配置。

## 环境要求

### 后端

| 组件 | 版本要求 |
|------|---------|
| Python | 3.10+ |
| pip | 最新版 |
| LangGraph | 0.2+（可选） |

### 前端

| 组件 | 版本要求 |
|------|---------|
| Node.js | 18+ |
| npm | 9+ |

---

## 配置说明

### 环境变量配置

创建 `.env` 文件：

```bash
# === 必需配置 ===
DASHSCOPE_API_KEY=sk-your-actual-api-key  # 阿里云 DashScope API Key

# === LLM 配置 ===
LLM_MODEL=qwen-turbo          # 模型：qwen-turbo, qwen-plus, qwen-max
MAX_LOOP=15                   # ReAct 最大循环次数
MAX_REACT_TURNS=20            # v2 工作流最大轮次

# === 服务配置 ===
API_HOST=127.0.0.1            # 服务主机（生产环境改为实际 IP）
API_PORT=5001                 # 服务端口

# === Checkpoint 配置 ===
CHECKPOINT_PERSISTENCE=sqlite # 持久化方式：memory, sqlite, postgres
SQLITE_DB_PATH=./checkpoints.db  # SQLite 数据库路径

# === 人工审批配置 ===
HUMAN_APPROVAL_ENABLED=false  # 是否启用人工审批
HUMAN_APPROVAL_FOR_VOUCHERS=false  # 凭证生成后是否强制审批
HUMAN_APPROVAL_TIMEOUT=3600   # 审批超时（秒）

# === RAG 知识库配置 ===
RAG_ENABLED=false             # 是否启用 RAG
KNOWLEDGE_DIR=./agent/knowledge/chunks  # 知识库目录
VECTOR_STORE_TYPE=chroma      # 向量存储：chroma, faiss
RAG_TOP_K=5                   # 检索条数
RERANK_ENABLED=false          # 是否启用重排序
```

---

## 开发环境部署

### 1. 安装依赖

```bash
# 后端依赖
cd 财务智能体
pip install -r requirements.txt

# 前端依赖
cd web
npm install
```

### 2. 配置 API Key

编辑 `.env` 文件，填入 DashScope API Key。

### 3. 启动服务

**方式一：一键启动**

```bash
启动全部.bat
```

**方式二：分别启动**

```bash
# 后端
python -m agent.server

# 前端
cd web
npm run dev
```

### 4. 访问

- 前端：http://localhost:3000
- 后端 API：http://127.0.0.1:5001
- API 文档：http://127.0.0.1:5001/docs

---

## 生产环境部署

### 方案一：直接运行

```bash
# 使用生产配置启动后端
python -m agent.server --host 0.0.0.0 --port 5001

# 构建并运行前端
cd web
npm run build
npm run preview  # 或使用 nginx 反向代理
```

### 方案二：Docker 部署

#### Dockerfile（后端）

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY agent/ ./agent/
COPY .env ./

# 启动服务
CMD ["python", "-m", "agent.server"]
```

#### Dockerfile（前端）

```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY web/package.json web/package-lock.json* ./
RUN npm ci

COPY web/ ./
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "preview"]
```

#### docker-compose.yml

```yaml
version: '3.8'

services:
  backend:
    build: .
    ports:
      - "5001:5001"
    environment:
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
    volumes:
      - ./uploads:/app/uploads
      - ./sessions.db:/app/sessions.db

  frontend:
    build: ./web
    ports:
      - "3000:3000"
    environment:
      - NUXT_PUBLIC_API_BASE=http://backend:5001
    depends_on:
      - backend
```

### 方案三：Nginx 反向代理

#### nginx.conf

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }

    # 后端 API
    location /api/ {
        proxy_pass http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # SSE 流式接口
    location /api/agent/chat/stream {
        proxy_pass http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        chunked_transfer_encoding off;
    }

    # 文件下载
    location /download {
        proxy_pass http://127.0.0.1:5001;
    }
}
```

---

## 性能优化

### 后端优化

1. **使用 SQLite Checkpoint**：设置 `CHECKPOINT_PERSISTENCE=sqlite`
2. **多 Worker**：Uvicorn 多进程运行（注意 SQLite 不支持多进程并发）
3. **异步处理**：对于大型文件处理，考虑使用后台任务

### 前端优化

1. **静态资源缓存**：Nuxt 自动处理
2. **CDN 加速**：将静态资源部署到 CDN
3. **压缩传输**：Nginx gzip 配置

---

## 安全配置

### API Key 安全

- 不要将 `.env` 文件提交到版本控制
- 生产环境使用环境变量或密钥管理服务

### CORS 配置

修改 `agent/server.py`：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],  # 限制允许的域名
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 文件上传限制

FastAPI 默认不限制文件大小，建议添加：

```python
from fastapi import UploadFile, File, Form
from fastapi.exceptions import HTTPException

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def validate_file_size(file: UploadFile):
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "文件过大，最大 10MB")
    await file.seek(0)
```

---

## 监控与日志

### 日志配置

已在 `agent/middleware/logging.py` 中实现结构化日志。

### 健康检查

```bash
curl http://127.0.0.1:5001/health
```

### Session 监控

```bash
curl http://127.0.0.1:5001/api/sessions
```

---

## 常见问题

### Q: 启动时报缺少配置错误

确保 `.env` 文件存在且 `DASHSCOPE_API_KEY` 已设置。

### Q: 前端无法连接后端

检查 `web/nuxt.config.ts` 中的 `NUXT_PUBLIC_API_BASE` 配置。

### Q: 凭证生成失败

检查上传的文件是否为金蝶云格式的 Excel 文件，查看错误码判断具体原因。

---

## 运行测试

```bash
# 运行所有测试
pytest tests/

# 只运行单元测试
pytest tests/ -m "not integration"

# 运行集成测试（需要启动服务）
pytest tests/integration/ -m integration
```