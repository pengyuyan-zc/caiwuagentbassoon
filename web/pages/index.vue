<template>
  <div class="app-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-logo">
        <div class="logo-icon">R</div>
        <div class="logo-text">
          <h1>锐博集团</h1>
          <span>财务智能体</span>
        </div>
      </div>

      <!-- 会话列表 -->
      <div class="session-section">
        <div class="session-header">
          <span class="session-title">会话记录</span>
          <button class="btn btn-ghost btn-sm" @click="createNewSession" title="新建会话">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </button>
        </div>
        <div class="session-list">
          <div
            v-for="s in sessions"
            :key="s.session_id"
            class="session-item"
            :class="{ active: currentSessionId === s.session_id }"
            @click="switchSession(s.session_id)"
          >
            <span class="session-dot"></span>
            <span class="session-label">{{ formatSessionLabel(s) }}</span>
            <button class="btn-delete-session" @click.stop="deleteSession(s.session_id)" title="删除会话">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <nav class="sidebar-nav">
        <div class="nav-section">
          <div class="nav-title">功能模块</div>
          <div
            v-for="item in navItems"
            :key="item.id"
            class="nav-item"
            :class="{ active: currentTab === item.id }"
            @click="currentTab = item.id"
          >
            <span class="nav-icon" v-html="item.icon"></span>
            <span class="nav-text">{{ item.label }}</span>
          </div>
        </div>
      </nav>

      <div class="sidebar-footer">
        <div class="status-badge" :class="{ 'status-warning': checkpointType === 'memory' }">
          <div class="status-dot"></div>
          <span>{{ checkpointType === 'memory' ? '会话不持久化' : '会话已持久化' }}</span>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 顶部标题 -->
      <header class="top-bar">
        <div class="top-bar-title">
          <h2>{{ currentNavItem?.title }}</h2>
          <p>{{ currentNavItem?.desc }}</p>
        </div>
        <div class="top-bar-actions">
          <span class="badge badge-blue">LangGraph v2</span>
          <span class="badge badge-purple" v-if="currentNode">节点: {{ currentNode }}</span>
        </div>
      </header>

      <!-- 聊天界面 -->
      <div class="chat-wrapper">
        <!-- 搜索框 -->
        <div v-if="messages.length > 0" class="search-bar">
          <button class="btn btn-ghost btn-sm" @click="showSearch = !showSearch" title="搜索消息">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          </button>
          <input
            v-if="showSearch"
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="搜索消息内容..."
          />
          <span v-if="showSearch && searchQuery" class="search-count">
            {{ filteredMessages.length }} / {{ messages.length }}
          </span>
        </div>

        <!-- 消息列表 -->
        <div class="chat-messages" ref="chatMessagesRef">
          <div v-if="messages.length === 0" class="chat-empty">
            <div class="chat-empty-icon">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <p class="chat-empty-title">开始对话</p>
            <p class="chat-empty-desc">告诉我您想做什么，例如：</p>
            <div class="chat-empty-hints">
              <span class="hint-chip" @click="sendHint('介绍一下财务智能体的功能')">
                了解系统功能
              </span>
              <span class="hint-chip" @click="sendHint('本月税务申报有哪些注意事项？')">
                税务咨询
              </span>
            </div>
          </div>

          <!-- 消息列表 -->
          <div
            v-for="(msg, idx) in filteredMessages"
            :key="idx"
            class="message-item"
            :class="msg.role"
          >
            <div class="message-avatar">
              <span v-if="msg.role === 'user'">👤</span>
              <span v-else>🤖</span>
            </div>
            <div class="message-body">
              <!-- 节点执行指示器 -->
              <div v-if="msg.node" class="node-indicator">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83"/>
                </svg>
                {{ msg.node }}
              </div>

              <!-- 内容 -->
              <div class="message-content" v-html="renderContent(msg.content)"></div>

              <!-- 工具调用结果卡片 -->
              <div v-if="msg.toolResult" class="tool-result-card">
                <div class="tool-result-header">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                  </svg>
                  工具执行结果
                </div>
                <div class="tool-result-body">
                  <div v-if="msg.toolResult.loading" class="tool-loading">
                    <div class="typing-dots"><span></span><span></span><span></span></div>
                    正在执行工具...
                  </div>
                  <div v-else-if="msg.toolResult.success" class="tool-success">
                    <pre class="code-block">{{ msg.toolResult.data }}</pre>
                    <button
                      v-if="msg.toolResult.downloadUrl"
                      class="btn btn-secondary"
                      style="margin-top: 12px; font-size: 13px;"
                      @click="downloadFile(msg.toolResult.downloadUrl)"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7,10 12,15 17,10"/><line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                      下载凭证文件
                    </button>
                  </div>
                  <div v-else class="tool-error">
                    <span style="color: var(--accent-red);">执行失败：</span>{{ msg.toolResult.error }}
                  </div>
                </div>
              </div>

              <!-- 加载中 -->
              <div v-if="msg.loading" class="typing-indicator">
                <div class="typing-dots"><span></span><span></span><span></span></div>
                AI 正在思考中...
              </div>
            </div>
          </div>
        </div>

        <!-- 审批弹窗 -->
        <div v-if="showApprovalModal" class="approval-overlay" @click.self="closeApprovalModal">
          <div class="approval-modal">
            <div class="approval-header">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="color: var(--accent-yellow)">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <span>凭证生成完成，请人工确认</span>
            </div>
            <div class="approval-body">
              <div class="approval-summary">
                <div class="approval-stat">
                  <span class="stat-value">{{ approvalData?.voucher_count ?? 0 }}</span>
                  <span class="stat-label">凭证数量</span>
                </div>
                <div class="approval-stat">
                  <span class="stat-value">{{ approvalData?.line_count ?? 0 }}</span>
                  <span class="stat-label">分录数量</span>
                </div>
                <div class="approval-stat">
                  <span class="stat-value">{{ approvalData?.tool ?? '-' }}</span>
                  <span class="stat-label">工具</span>
                </div>
              </div>
              <div v-if="approvalData?.message" class="approval-message">
                {{ approvalData.message }}
              </div>
              <div class="approval-message-text">
                请确认凭证信息是否正确，确认后将自动下载凭证文件。
              </div>
            </div>
            <div class="approval-footer">
              <button class="btn btn-secondary" @click="rejectApproval">取消</button>
              <button class="btn btn-primary" @click="confirmApproval">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="20,6 9,17 4,12"/>
                </svg>
                确认生成
              </button>
            </div>
          </div>
        </div>

        <!-- 文件上传区 -->
        <div class="upload-area" v-if="showUpload">
          <div
            class="upload-zone"
            :class="{ dragover: isDragging }"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="handleDrop"
            @click="triggerUpload"
          >
            <input
              ref="fileInputRef"
              type="file"
              accept=".xlsx,.xls"
              multiple
              @change="handleFileChange"
            />
            <div class="upload-icon">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="1.5">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17,8 12,3 7,8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <div class="upload-text">点击或拖拽上传 Excel 文件（支持多选）</div>
            <div class="upload-hint">支持 .xlsx .xls 格式，可一次选择多个文件</div>
          </div>
          <div v-if="uploadedFiles.length > 0" class="file-list">
            <div v-for="(file, idx) in uploadedFiles" :key="idx" class="file-info">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;color:var(--accent-green)">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>
              </svg>
              <span class="file-name">{{ file.name }}</span>
              <span class="file-size">{{ formatSize(file.size) }}</span>
              <button class="btn btn-ghost" style="padding: 2px 6px; font-size: 11px;" @click.stop="removeFile(idx)">移除</button>
            </div>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="input-area">
          <div class="input-row">
            <textarea
              v-model="inputText"
              class="input"
              :placeholder="currentNavItem?.placeholder || '输入您的问题，按 Enter 发送，Shift+Enter 换行...'"
              rows="1"
              @keydown.enter.exact.prevent="sendMessage"
              @input="autoResize"
            ></textarea>
            <button
              class="btn btn-primary send-btn"
              :disabled="!inputText.trim() || isLoading"
              @click="sendMessage"
            >
              <svg v-if="!isLoading" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22,2 15,22 11,13 2,9"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="animate-spin">
                <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
              </svg>
            </button>
          </div>
          <div class="input-hint">
            <span class="hint-link" @click="showUpload = !showUpload">
              {{ showUpload ? '收起上传' : '+ 上传 Excel 文件（可多选）' }}
            </span>
            <span>Enter 发送 · Shift+Enter 换行</span>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from 'vue'

const config = useRuntimeConfig()

// ══════════════════════════════════════════════════════════════════════════
// 状态
// ══════════════════════════════════════════════════════════════════════════

const currentTab = ref('chat')
const messages = ref<any[]>([])
const inputText = ref('')
const isLoading = ref(false)
const showUpload = ref(false)
const uploadedFiles = ref<Array<{ name: string; size: number; file: File }>>([])
const isDragging = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const chatMessagesRef = ref<HTMLElement | null>(null)

// ── Session 管理 ──────────────────────────────────────────────────────
const SESSION_KEY = 'finance_agent_session_id'
const sessions = ref<any[]>([])
const currentSessionId = ref('')
const checkpointType = ref('memory')

// ── 审批弹窗 ──────────────────────────────────────────────────────────
const showApprovalModal = ref(false)
const approvalData = ref<any>(null)
const pendingApprovalSessionId = ref('')

// ── 节点执行状态 ──────────────────────────────────────────────────────
const currentNode = ref('')

// ── 搜索功能 ──────────────────────────────────────────────────────
const searchQuery = ref('')
const showSearch = ref(false)

const filteredMessages = computed(() => {
  if (!searchQuery.value.trim()) return messages.value
  const query = searchQuery.value.toLowerCase()
  return messages.value.filter(msg =>
    msg.content?.toLowerCase().includes(query) ||
    msg.node?.toLowerCase().includes(query)
  )
})

// ══════════════════════════════════════════════════════════════════════════
// 错误码友好提示
// ══════════════════════════════════════════════════════════════════════════

const ERROR_MESSAGES: Record<string, string> = {
  'FILE_FORMAT_ERROR': '文件格式不正确，请上传金蝶云导出的 Excel 文件（.xlsx）',
  'FILE_NOT_FOUND': '文件不存在，请重新上传',
  'SKILL_NOT_FOUND': '未找到对应的处理工具',
  'TOOL_NOT_FOUND': '工具函数不存在',
  'MISSING_PARAMETER': '缺少必需参数',
  'LLM_CONNECTION_ERROR': 'AI 服务连接失败，请稍后重试',
  'LLM_TIMEOUT_ERROR': 'AI 服务响应超时，请稍后重试',
  'LLM_RATE_LIMIT_ERROR': '请求过于频繁，请稍后再试',
  'SESSION_NOT_FOUND': '会话不存在或已过期，请刷新页面',
  'SESSION_EXPIRED': '会话已过期，请重新开始',
  'VALIDATION_ERROR': '请求参数验证失败',
  'MISSING_CONFIG': '系统配置不完整，请联系管理员',
  'CONFIG_ERROR': '系统配置错误，请联系管理员',
}

function getFriendlyErrorMessage(code: string, originalMessage: string): string {
  const friendlyMsg = ERROR_MESSAGES[code]
  if (friendlyMsg) {
    return `❌ ${friendlyMsg}\n\n_详细信息：${originalMessage}_`
  }
  return `❌ ${originalMessage}`
}

// ══════════════════════════════════════════════════════════════════════════
// 导航
// ══════════════════════════════════════════════════════════════════════════

const navItems = [
  {
    id: 'chat', label: '智能问答',
    title: '智能问答',
    desc: '基于 LangGraph v2 多节点工作流，支持人工审批和知识增强',
    placeholder: '输入您的问题，按 Enter 发送...',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`
  },
  {
    id: 'skills', label: '可用工具列表',
    title: '可用 Skills 工具',
    desc: '查看 Agent 已注册的所有 Skills 工具',
    placeholder: '',
    icon: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>`
  }
]

const currentNavItem = computed(() => navItems.find(n => n.id === currentTab.value))

// ══════════════════════════════════════════════════════════════════════════
// Session 管理函数
// ══════════════════════════════════════════════════════════════════════════

function generateSessionId() {
  return 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8)
}

async function loadSessions() {
  try {
    const res = await fetch(`${config.public.apiBase}/api/sessions`)
    const data = await res.json()
    sessions.value = data.sessions || []
  } catch { /* ignore */ }
}

async function createNewSession() {
  const formData = new FormData()
  formData.append('user_id', 'default')
  formData.append('metadata', JSON.stringify({ created_from: 'frontend' }))
  try {
    const res = await fetch(`${config.public.apiBase}/api/sessions`, {
      method: 'POST',
      body: formData
    })
    const data = await res.json()
    if (data.session_id) {
      currentSessionId.value = data.session_id
      localStorage.setItem(SESSION_KEY, data.session_id)
      messages.value = []
      await loadSessions()
    }
  } catch (err) {
    console.error('创建会话失败', err)
  }
}

async function switchSession(sessionId: string) {
  if (currentSessionId.value === sessionId) return
  currentSessionId.value = sessionId
  localStorage.setItem(SESSION_KEY, sessionId)
  messages.value = []
  await loadSessionHistory(sessionId)
}

async function loadSessionHistory(sessionId: string) {
  try {
    const res = await fetch(`${config.public.apiBase}/api/sessions/${sessionId}`)
    if (!res.ok) return
    const session = await res.json()
    if (session.metadata) {
      try {
        const meta = JSON.parse(session.metadata)
        if (meta.messages) {
          messages.value = meta.messages
        }
      } catch { /* ignore */ }
    }
  } catch { /* ignore */ }
}

async function deleteSession(sessionId: string) {
  if (!confirm('确定删除该会话？')) return
  try {
    await fetch(`${config.public.apiBase}/api/sessions/${sessionId}`, { method: 'DELETE' })
    if (currentSessionId.value === sessionId) {
      await createNewSession()
    }
    await loadSessions()
  } catch (err) {
    console.error('删除会话失败', err)
  }
}

function formatSessionLabel(session: any) {
  const updated = session.updated_at
  if (!updated) return '新会话'
  const d = new Date(updated)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// ══════════════════════════════════════════════════════════════════════════
// 发送消息
// ══════════════════════════════════════════════════════════════════════════

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content: text, node: '' })

  const aiMsg: any = { role: 'assistant', content: '', loading: true, node: '', toolResult: null }
  messages.value.push(aiMsg)

  await scrollToBottom()

  const formData = new FormData()
  formData.append('message', text)
  formData.append('session_id', currentSessionId.value)
  for (const item of uploadedFiles.value) {
    formData.append('files', item.file)
  }
  uploadedFiles.value = []
  showUpload.value = false
  isLoading.value = true
  currentNode.value = ''

  try {
    const response = await fetch(`${config.public.apiBase}/api/agent/chat/stream`, {
      method: 'POST',
      body: formData
    })

    if (!response.ok) {
      aiMsg.content = `服务器错误 ${response.status}`
      aiMsg.loading = false
      isLoading.value = false
      return
    }

    if (!response.body) {
      aiMsg.content = '服务器返回空响应体'
      aiMsg.loading = false
      isLoading.value = false
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''
    let currentData = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      let lineEnd
      while ((lineEnd = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, lineEnd).replace(/\r$/, '')
        buffer = buffer.slice(lineEnd + 1)

        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          currentData = line.slice(5)
        } else if (line === '') {
          if (!currentData.trim()) {
            currentEvent = ''
            currentData = ''
            continue
          }
          try {
            const jsonData = JSON.parse(currentData.trim())

            if (currentEvent === 'content' && jsonData.content) {
              aiMsg.content += jsonData.content
              if (jsonData.node) {
                aiMsg.node = jsonData.node
                currentNode.value = jsonData.node
              }
              await scrollToBottom()
            } else if (currentEvent === 'tools' && jsonData.tools) {
              console.log('[SSE] 使用了工具:', jsonData.tools)
            } else if (currentEvent === 'approval') {
              // 收到审批请求 → 弹出审批弹窗
              approvalData.value = jsonData
              pendingApprovalSessionId.value = currentSessionId.value
              showApprovalModal.value = true
            } else if (currentEvent === 'done') {
              if (!aiMsg.content && jsonData.reply) {
                aiMsg.content = jsonData.reply
              }
              if (jsonData.download_url) {
                aiMsg.toolResult = {
                  success: true,
                  data: '凭证生成成功',
                  downloadUrl: jsonData.download_url
                }
              }
              // 更新 checkpoint type
              if (jsonData.checkpoint_type) {
                checkpointType.value = jsonData.checkpoint_type
              }
            } else if (currentEvent === 'error') {
              // 结构化错误处理
              const errorCode = jsonData.code || jsonData.error?.code || 'UNKNOWN_ERROR'
              const errorMessage = jsonData.message || jsonData.error?.message || jsonData.error || '未知错误'
              aiMsg.content = getFriendlyErrorMessage(errorCode, errorMessage)
              aiMsg.errorCode = errorCode
              aiMsg.loading = false
              isLoading.value = false
              await scrollToBottom()
              return
            }
          } catch (e) {
            // 非 JSON 数据，忽略
          }
          currentEvent = ''
          currentData = ''
        }
      }
    }

    aiMsg.loading = false
    currentNode.value = ''

    // 保存消息到 session metadata（持久化）
    await saveMessagesToSession()

  } catch (err: any) {
    aiMsg.loading = false
    aiMsg.content = `网络错误：${err.message}`
    currentNode.value = ''
  }

  isLoading.value = false
  await scrollToBottom()
}

async function saveMessagesToSession() {
  if (!currentSessionId.value) return
  try {
    await fetch(`${config.public.apiBase}/api/sessions/${currentSessionId.value}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ metadata: JSON.stringify({ messages: messages.value }) })
    })
  } catch { /* ignore */ }
}

// ══════════════════════════════════════════════════════════════════════════
// 审批接口
// ══════════════════════════════════════════════════════════════════════════

async function confirmApproval() {
  showApprovalModal.value = false
  if (!pendingApprovalSessionId.value) return

  const formData = new FormData()
  formData.append('session_id', pendingApprovalSessionId.value)
  formData.append('action', 'approve')

  try {
    const res = await fetch(`${config.public.apiBase}/api/agent/approve`, {
      method: 'POST',
      body: formData
    })
    const data = await res.json()
    if (data.resumed) {
      messages.value.push({
        role: 'assistant',
        content: '✅ 已确认，继续处理...',
        node: 'human_approval',
        loading: true,
        toolResult: null,
      })
      // 继续流式获取结果
      await resumeStream(pendingApprovalSessionId.value)
    } else {
      messages.value.push({
        role: 'assistant',
        content: `审批确认失败：${data.message}`,
        node: 'human_approval',
        loading: false,
      })
    }
  } catch (err) {
    messages.value.push({
      role: 'assistant',
      content: `网络错误：${err}`,
      node: 'human_approval',
    })
  }

  approvalData.value = null
  pendingApprovalSessionId.value = ''
  await scrollToBottom()
}

async function rejectApproval() {
  showApprovalModal.value = false
  if (!pendingApprovalSessionId.value) return

  const formData = new FormData()
  formData.append('session_id', pendingApprovalSessionId.value)
  formData.append('action', 'reject')

  try {
    await fetch(`${config.public.apiBase}/api/agent/approve`, {
      method: 'POST',
      body: formData
    })
  } catch { /* ignore */ }

  messages.value.push({
    role: 'assistant',
    content: '❌ 已取消本次凭证生成。',
    node: 'human_approval',
    loading: false,
  })

  approvalData.value = null
  pendingApprovalSessionId.value = ''
  await scrollToBottom()
}

function closeApprovalModal() {
  showApprovalModal.value = false
  approvalData.value = null
  pendingApprovalSessionId.value = ''
}

async function resumeStream(sessionId: string) {
  // 审批确认后，通过普通的 chat 接口继续获取结果（session 会自动从 checkpoint 恢复）
  const formData = new FormData()
  formData.append('message', '继续执行')
  formData.append('session_id', sessionId)

  const aiMsg: any = { role: 'assistant', content: '', loading: true, node: 'model', toolResult: null }
  messages.value.push(aiMsg)
  isLoading.value = true
  currentNode.value = 'model'

  try {
    const response = await fetch(`${config.public.apiBase}/api/agent/chat/stream`, {
      method: 'POST',
      body: formData
    })
    if (!response.body) return

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''
    let currentData = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      let lineEnd
      while ((lineEnd = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, lineEnd).replace(/\r$/, '')
        buffer = buffer.slice(lineEnd + 1)
        if (line.startsWith('event:')) currentEvent = line.slice(6).trim()
        else if (line.startsWith('data:')) currentData = line.slice(5)
        else if (line === '' && currentData.trim()) {
          try {
            const jsonData = JSON.parse(currentData.trim())
            if (currentEvent === 'content' && jsonData.content) {
              aiMsg.content += jsonData.content
              if (jsonData.node) {
                aiMsg.node = jsonData.node
                currentNode.value = jsonData.node
              }
              await scrollToBottom()
            } else if (currentEvent === 'done') {
              if (!aiMsg.content && jsonData.reply) aiMsg.content = jsonData.reply
              if (jsonData.download_url) {
                aiMsg.toolResult = { success: true, data: '凭证生成成功', downloadUrl: jsonData.download_url }
              }
            }
          } catch { /* ignore */ }
          currentEvent = ''
          currentData = ''
        }
      }
    }
  } catch { /* ignore */ }

  aiMsg.loading = false
  isLoading.value = false
  currentNode.value = ''
  await scrollToBottom()
}

// ══════════════════════════════════════════════════════════════════════════
// Skills 列表
// ══════════════════════════════════════════════════════════════════════════

watch(currentTab, async (tab) => {
  if (tab === 'skills') {
    try {
      const res = await fetch(`${config.public.apiBase}/api/agent/skills`)
      const data = await res.json()
      messages.value.push({
        role: 'assistant',
        content: `已注册 Skills 工具：\n\n${data.skills?.map((s: any) => `• **${s.name}** - ${s.description || '无描述'}`).join('\n') || '暂无'}`
      })
    } catch {
      messages.value.push({
        role: 'assistant',
        content: '无法获取工具列表，请确认后端服务已启动（http://127.0.0.1:5001）'
      })
    }
    currentTab.value = 'chat'
  }
})

// ══════════════════════════════════════════════════════════════════════════
// 文件上传
// ══════════════════════════════════════════════════════════════════════════

function triggerUpload() { fileInputRef.value?.click() }

function handleFileChange(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (files) {
    for (const file of Array.from(files)) {
      if (!uploadedFiles.value.some(f => f.name === file.name)) {
        uploadedFiles.value.push({ name: file.name, size: file.size, file })
      }
    }
    showUpload.value = true
  }
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (files) {
    for (const file of Array.from(files)) {
      if ((file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) &&
          !uploadedFiles.value.some(f => f.name === file.name)) {
        uploadedFiles.value.push({ name: file.name, size: file.size, file })
      }
    }
    showUpload.value = true
  }
}

function removeFile(idx: number) {
  uploadedFiles.value.splice(idx, 1)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

// ══════════════════════════════════════════════════════════════════════════
// 工具函数
// ══════════════════════════════════════════════════════════════════════════

function sendHint(text: string) {
  inputText.value = text
  sendMessage()
}

async function scrollToBottom() {
  await nextTick()
  if (chatMessagesRef.value) {
    chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
  }
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

function renderContent(content: string): string {
  if (!content) return ''
  return content
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code style="background:rgba(59,130,246,0.1);padding:1px 6px;border-radius:4px;font-size:12px;color:#60a5fa;">$1</code>')
}

function downloadFile(url: string) { window.open(url, '_blank') }

// ══════════════════════════════════════════════════════════════════════════
// 初始化
// ══════════════════════════════════════════════════════════════════════════

onMounted(async () => {
  // 初始化或恢复 session
  let savedSessionId = localStorage.getItem(SESSION_KEY)
  if (savedSessionId) {
    try {
      const res = await fetch(`${config.public.apiBase}/api/sessions/${savedSessionId}`)
      if (res.ok) {
        currentSessionId.value = savedSessionId
      } else {
        savedSessionId = null
      }
    } catch { savedSessionId = null }
  }

  if (!savedSessionId) {
    // 创建新会话
    await createNewSession()
  } else {
    currentSessionId.value = savedSessionId
    await loadSessionHistory(savedSessionId)
  }

  await loadSessions()

  // 获取 checkpoint 类型
  try {
    const res = await fetch(`${config.public.apiBase}/health`)
    const data = await res.json()
    checkpointType.value = data.checkpoint_persistence || 'memory'
  } catch { /* ignore */ }
})
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ── 侧边栏 ── */
.sidebar {
  width: 240px;
  min-width: 240px;
  background: rgba(15, 23, 42, 0.98);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  z-index: 10;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px 20px;
  border-bottom: 1px solid var(--border);
}

.logo-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  color: white;
  flex-shrink: 0;
}

.logo-text h1 { font-size: 16px; font-weight: 700; color: var(--text-primary); line-height: 1.2; margin: 0; }
.logo-text span { font-size: 11px; color: var(--text-muted); }

/* ── Session 列表 ── */
.session-section {
  padding: 12px 12px 8px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.session-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.btn-sm {
  padding: 4px 6px;
  font-size: 12px;
  line-height: 1;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 160px;
  overflow-y: auto;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 12px;
  transition: all 0.15s;
}

.session-item:hover { background: rgba(255,255,255,0.06); color: var(--text-primary); }
.session-item.active { background: rgba(59, 130, 246, 0.15); color: var(--accent-blue-light); }

.session-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}

.session-item.active .session-dot { background: var(--accent-blue); }

.session-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.btn-delete-session {
  opacity: 0;
  padding: 2px;
  color: var(--text-muted);
  transition: opacity 0.15s;
}

.session-item:hover .btn-delete-session { opacity: 1; }
.btn-delete-session:hover { color: var(--accent-red); }

/* ── Nav ── */
.sidebar-nav { flex: 1; padding: 12px 12px; overflow-y: auto; }
.nav-section { margin-bottom: 8px; }
.nav-title {
  font-size: 10px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 1px; padding: 0 12px; margin-bottom: 6px;
}
.nav-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  border-radius: var(--radius-md); cursor: pointer; color: var(--text-secondary);
  transition: all 0.15s; margin-bottom: 2px;
}
.nav-item:hover { background: rgba(59, 130, 246, 0.08); color: var(--text-primary); }
.nav-item.active {
  background: rgba(59, 130, 246, 0.15); color: var(--accent-blue-light);
  border: 1px solid rgba(59, 130, 246, 0.2);
}
.nav-icon { display: flex; align-items: center; justify-content: center; width: 20px; flex-shrink: 0; }
.nav-text { font-size: 13px; font-weight: 500; }

/* ── 状态徽章 ── */
.sidebar-footer { padding: 16px; border-top: 1px solid var(--border); }
.status-badge {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.15); border-radius: var(--radius-md);
}
.status-badge.status-warning {
  background: rgba(245, 158, 11, 0.08);
  border-color: rgba(245, 158, 11, 0.15);
}
.status-badge.status-warning .status-dot { background: var(--accent-yellow); }
.status-badge.status-warning span { color: var(--accent-yellow); }
.status-dot {
  width: 7px; height: 7px; background: var(--accent-green);
  border-radius: 50%; animation: pulse 2s ease-in-out infinite;
}
.status-badge span { font-size: 12px; color: var(--accent-green); font-weight: 500; }

/* ── 主内容区 ── */
.main-content {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  background: linear-gradient(160deg, #0f172a 0%, #1a2540 50%, #0f172a 100%);
}

.top-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20px 32px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.top-bar-title h2 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin-bottom: 2px; }
.top-bar-title p { font-size: 13px; color: var(--text-muted); }
.top-bar-actions { display: flex; gap: 8px; align-items: center; }

/* ── 聊天区 ── */
.chat-wrapper { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 0 32px; }
.chat-messages { flex: 1; overflow-y: auto; padding: 24px 0; display: flex; flex-direction: column; gap: 20px; }

/* 搜索框 */
.search-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 0; flex-shrink: 0;
}
.search-input {
  flex: 1; max-width: 300px;
  padding: 8px 12px;
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 13px;
}
.search-input:focus {
  outline: none;
  border-color: var(--accent-blue);
  background: rgba(59, 130, 246, 0.08);
}
.search-count {
  font-size: 12px; color: var(--text-muted);
  padding: 4px 8px;
  background: rgba(255,255,255,0.04);
  border-radius: 4px;
}

/* 节点指示器 */
.node-indicator {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px; margin-bottom: 6px;
  background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: 99px; font-size: 11px; color: var(--accent-blue-light);
}

/* 审批弹窗 */
.approval-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.7); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
}

.approval-modal {
  background: var(--bg-primary); border: 1px solid var(--border);
  border-radius: var(--radius-lg); width: 480px; max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
  overflow: hidden;
}

.approval-header {
  display: flex; align-items: center; gap: 12px;
  padding: 20px 24px;
  background: rgba(245, 158, 11, 0.08);
  border-bottom: 1px solid rgba(245, 158, 11, 0.15);
  font-size: 16px; font-weight: 600; color: var(--accent-yellow);
}

.approval-body { padding: 24px; }

.approval-summary {
  display: flex; gap: 24px; margin-bottom: 20px;
}

.approval-stat {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
}

.stat-value {
  font-size: 28px; font-weight: 700; color: var(--text-primary);
}

.stat-label { font-size: 12px; color: var(--text-muted); }

.approval-message {
  padding: 12px 16px; background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.15);
  border-radius: var(--radius-md); font-size: 13px; color: var(--text-secondary);
  margin-bottom: 16px;
}

.approval-message-text {
  font-size: 13px; color: var(--text-muted);
}

.approval-footer {
  display: flex; justify-content: flex-end; gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
}

/* 底部 */
.input-area { padding: 16px 0 24px; flex-shrink: 0; }
.input-row { display: flex; gap: 10px; align-items: flex-end; }
.input-row .input { flex: 1; max-height: 200px; overflow-y: auto; }
.send-btn { padding: 12px 16px; flex-shrink: 0; }
.input-hint {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 8px; font-size: 12px; color: var(--text-muted);
}
.hint-link { cursor: pointer; color: var(--accent-blue-light); transition: color 0.15s; }
.hint-link:hover { color: var(--text-primary); }

/* ── 响应式 ── */
@media (max-width: 768px) {
  .sidebar { width: 60px; min-width: 60px; }
  .logo-text, .nav-text, .nav-title, .sidebar-footer .status-badge span,
  .session-title, .session-label { display: none; }
  .sidebar-logo { justify-content: center; padding: 16px 0; }
  .logo-icon { margin: 0; }
  .nav-item { justify-content: center; padding: 12px; }
}
</style>
