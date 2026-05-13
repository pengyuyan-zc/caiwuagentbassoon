# 财务智能体 - LangGraph ReAct Agent

基于 **LangGraph** 框架搭建的 **ReAct 智能体**，动态加载 Skills 技能工具，前端使用 Vue + Nuxt 展示聊天界面。

> **启动前端：** `npm run dev`  
> **启动后端：** `D:/xuexi/anaconda/python.exe f:/xiangmu/pythonProject6（ruibo）/invoice-tax-agent/开票主体税务凭证生成.py`

---

## 系统架构

```
用户输入 → LangGraph ReAct Agent → LLM (qwen-turbo)
                                   ↓
                             意图识别
                                   ↓
                        ┌──────────┴──────────┐
                        ↓                      ↓
                  不需要工具               需要调用工具
                  → 直接回复               → 执行 Skill
                                                ↓
                                   ┌────────────┼────────────┐
                                   ↓            ↓            ↓
                          invoice-tax    salary-tax    invoice-mgmt
                           voucher       voucher        voucher
                                                        ↓
                                                  salary-mgmt
                                                    voucher
```

---

## 核心能力 — 四大 Skills

本智能体当前内置 **4 个 Skill**，覆盖税务/管理两套账的开票凭证与工资报酬凭证生成，全部分布在 `agent/skills/` 目录下：

| Skill | 触发词示例 | 适用账簿 | 输入文件 |
|-------|-----------|---------|---------|
| **invoice-tax-voucher** | 生成开票税务凭证、X月开票税务凭证 | 税务帐 | 金蝶云格式开票主体 Excel |
| **salary-tax-voucher** | 生成工资税务凭证、X月工资凭证 | 税务帐 | 工资报酬支付申请审批表 |
| **salary-management-voucher** | 生成工资管理帐凭证、X月工资管理帐凭证 | 管理帐 | 工资报酬支付申请审批表 |
| **invoice-management-voucher** | 生成开票管理帐凭证、X月开票管理帐凭证 | 管理帐 | OA 开票申请数据 |

---

### Skill 1 — 开票主体税务凭证生成 (`invoice-tax-voucher`)

> **触发词：** 生成开票税务凭证、生成税务凭证、X月开票税务凭证、开票主体税务凭证、发票税务凭证  
> **输入：** 金蝶云格式开票主体 Excel 文件

#### 分录规则

**全额开票（3条分录）**

```
借  1122    应收账款           = 开票总额（填客户编码/名称）
贷  6001.xx 主营业务收入        = 不含税金额
贷  2221.01.02 销项税额         = 增值税金额（≠0 时才写）
```

**差额开票（4条分录）**

```
借  1122    应收账款            = 开票总额（填客户编码/名称）
贷  6001.xx 主营业务收入         = 不含税金额
贷  2221.01.02 销项税额          = 增值税金额（≠0 时才写）
贷  6001.xx 主营业务收入          = 差额开票金额（>0 时才写）
```

**无税额仅差额（2条分录）**

```
借  1122    应收账款            = 开票总额（填客户编码/名称）
贷  6001.xx 主营业务收入         = 差额开票金额
```

#### 业务类型 → 科目映射

| 内部类型分类 | 主营业务收入科目 |
|------------|--------------|
| 派遣业务 | 6001.02.00 |
| 代理业务 | 6001.03.01 |
| 承揽业务 / 小时间承揽 | 6001.04.01 |
| 其他未识别 | 6001.04.01（默认） |

#### 调用方式

```python
from agent import invoke_invoice_voucher

result = invoke_invoice_voucher(
    input_file="开票主体.xlsx",   # 开票主体Excel文件路径
    output_dir="输出目录"          # 可选，默认为输入文件同目录
)
```

#### 返回格式

```python
{
    'success': True,
    'output_file': '凭证输出_20260416_120000.xlsx',
    'voucher_count': 15,   # 凭证数量
    'line_count': 45,      # 分录数量
    'message': '生成完成！共 15 张凭证，2.3 秒'
}
```

---

### Skill 2 — 工资报酬税务凭证生成 (`salary-tax-voucher`)

> **触发词：** 生成工资税务凭证、生成工资报酬税务凭证、X月工资凭证、工资税务凭证  
> **输入：** 金蝶云格式工资报酬支付申请审批表

#### 分录规则

**派遣 / 代理 / 承揽业务（2-4条分录）**

```
借  6401.xx.xx  主营业务成本     = 实发工资（填客户名）
贷  1002         银行存款        = 实发工资（填客户名）

# 若有个税：
借  6401.xx.xx  主营业务成本      = 个税（摘要加"个税"）
贷  2221.13     应交税费_代扣个人所得税 = 个税
```

**助残业务（5条分录）**

```
借  6602.01.01.01  管理费用_人力成本_工资薪酬_工资 = 应发工资 - 税后扣除数
借  2211.01.01     应付职工薪酬_工资薪金_工资      = 实发工资
贷  2211.02.02     应付职工薪酬_社保_社保个人部分  = 社保和公积金个人部分
贷  2211.01.01     应付职工薪酬_工资薪金_工资      = 实发工资
贷  1002           银行存款                       = 实发工资（填客户名）
```

#### 业务类型 → 科目映射

| 合同业务类型 | 主营业务成本科目 |
|------------|--------------|
| 派遣业务 | 6401.04.01 |
| 承揽业务 | 6401.04.01 |
| 代理业务 | 6401.02.01 |
| 助残业务 | 6602.01.01.01（管理费用） |

#### 调用方式

```python
from agent import invoke_salary_tax_voucher

result = invoke_salary_tax_voucher(
    input_file="工资报酬支付申请.xlsx",
    output_dir="输出目录"
)
```

#### 返回格式

```python
{
    'success': True,
    'output_file': '工资报酬凭证.xlsx',
    'approval_count': 15,
    'entry_count': 45,
    'error_count': 0,
    'message': '生成完成！共 15 张凭证，45 条分录'
}
```

---

### Skill 3 — 工资报酬管理帐凭证生成 (`salary-management-voucher`)

> **触发词：** 生成工资管理帐凭证、生成工资报酬管理帐凭证、X月工资管理帐凭证、工资管理凭证  
> **输入：** 金蝶云格式工资报酬支付申请审批表

#### 分录规则

**承揽业务（2-4条分录）**

```
借  6401.04.01  主营业务成本      = 实发工资（填客户名）
贷  1002         银行存款         = 实发工资（填客户名）

# 若有个税：
借  6401.04.01  主营业务成本      = 个税（摘要加"个税"）
贷  2221.13     应交税费_代扣个人所得税 = 个税（填客户名）
```

**派遣 / 代理 / 假外包（广东公司，2-4条分录）**

```
借  2202.02.01  应付账款_代收代付款项_代付工资  = 实发工资（填客户名）
贷  1002         银行存款                      = 实发工资（填客户名）

# 若有个税：
借  2202.02.05  应付账款_代收代付款项_代付个税  = 个税（填客户名）
贷  2221.13     应交税费_代扣个人所得税         = 个税（填客户名）
```

**灵工业务（2条分录）**

```
借  2202.02.12  应付账款_代收代付款项_代付经营所得 = 实发工资（填客户名）
贷  1002         银行存款                        = 实发工资（填客户名）
```

**助残业务（2条分录）**

```
借  2202.01.05  应付账款_投保申报款项_待分配残疾人残保金费用 = 实发工资
贷  1002         银行存款                                        = 实发工资（填客户名）
```

**非广东公司（所有业务类型，2条分录）**

```
借  1221.01.03  其他应收款_内部公司往来_代交易往来款 = 实发工资（填客户名）
贷  1002         银行存款                           = 实发工资（填客户名）
```

#### 业务类型 → 科目映射

| 归属利润中心 | 内部业务类型 | 借方科目 | 贷方科目 |
|------------|------------|---------|---------|
| 广东公司 | 承揽业务 | 6401.04.01 | 1002 |
| 广东公司 | 派遣/代理/假外包 | 2202.02.01 | 1002 |
| 广东公司 | 灵工业务 | 2202.02.12 | 1002 |
| 广东公司 | 助残业务 | 2202.01.05 | 1002 |
| 其他 | 所有类型 | 1221.01.03 | 1002 |

#### 调用方式

```python
from agent import invoke_salary_management_voucher

result = invoke_salary_management_voucher(
    input_file="工资报酬支付申请.xlsx",
    output_dir="输出目录"
)
```

#### 返回格式

```python
{
    'success': True,
    'output_file': '工资发放管理帐凭证.xlsx',
    'approval_count': 15,
    'entry_count': 45,
    'error_count': 0,
    'message': '生成完成！共 15 张凭证，45 条分录'
}
```

---

### Skill 4 — 开票管理帐凭证生成 (`invoice-management-voucher`)

> **触发词：** 生成开票管理帐凭证、X月开票管理帐凭证、开票主体管理帐凭证、管理帐发票凭证  
> **输入：** OA 开票申请数据文件

#### 分录规则

每张发票（审批编号）生成一张凭证，含 2-3 条分录：

**广东谊丰（账簿 501）**

```
借  1122.xx    应收账款（按内部类型选子目） = 开票总额（填客户编码/名称）
贷  6001.xx    主营业务收入（按内部类型选子目） = 不含税金额
贷  2221.01.02 销项税额                        = 增值税金额（>0 时）
```

**非广东（账簿 102）** — 分录结构相同，账簿编码不同。

#### 业务类型 → 科目映射

| 内部类型分类 | 应收账款子目 | 主营业务收入科目 |
|------------|------------|---------------|
| 派遣业务 | 1122.02 | 6001.01 |
| 代理业务 | 1122.03 | 6001.02 |
| 承揽业务 | 1122.04 | 6001.03 |
| 猎头业务 | 1122.05 | 6001.04 |
| 灵工/小时间 | 1122.11 | 6001.10 |
| 未识别 | 1122.04（默认） | 6001.03（默认） |

#### 开票主体 → 账簿映射

| 开票主体 | 账簿编码 | 账簿名称 |
|---------|---------|---------|
| 广东谊丰 | 501 | 广东公司 |
| 其他 | 102 | 按主体名称 |

#### 调用方式

```python
from agent import invoke_management_voucher

result = invoke_management_voucher(
    input_file="OA开票申请.xlsx",
    output_dir="输出目录",
    template_file=None   # 可选，默认自动搜索
)
```

#### 返回格式

```python
{
    'success': True,
    'output_file': '管理帐凭证_20260430_113000.xlsx',
    'voucher_count': 15,
    'line_count': 45,
    'message': '生成完成！共 15 张凭证，3.2 秒'
}
```

---

## 目录结构

```
财务智能体/
├── agent/                          # Python Agent 核心
│   ├── finance_agent.py             # 入口，Agent 工厂
│   ├── graph.py                     # LangGraph ReAct 图
│   ├── react_simple.py             # 纯 Python ReAct（LangGraph 未安装时降级）
│   ├── helpers.py                  # 共享工具函数
│   ├── server.py                   # FastAPI 服务
│   └── skills/                      # ★ Skills 技能目录
│       ├── invoice-tax-voucher/     # Skill 1：开票税务凭证
│       ├── salary-tax-voucher/      # Skill 2：工资税务凭证
│       ├── salary-management-voucher/   # Skill 3：工资管理帐凭证
│       └── invoice-management-voucher/   # Skill 4：开票管理帐凭证
│
├── web/                            # Vue + Nuxt 前端
│   ├── pages/index.vue             # 聊天主页面
│   ├── components/                  # 组件
│   └── package.json
│
├── uploads/                        # 上传文件目录（自动创建）
├── requirements.txt                # Python 依赖
├── .env                           # 环境配置（API Key 等）
├── 启动全部.bat                    # 一键启动前后端
└── 启动后端.bat                   # 仅启动后端
```

---

## 快速启动

### 1. 安装 Python 依赖

```bash
cd F:\xiangmu\pythonProject6（ruibo）\财务智能体
pip install -r requirements.txt
```

### 2. 配置 API Key

编辑 `.env` 文件，填入阿里云 DashScope API Key：

```
DASHSCOPE_API_KEY=sk-your-key-here
LLM_MODEL=qwen-turbo   # 可选: qwen-turbo, qwen-plus, qwen-max
```

### 3. 启动服务

**方式一：一键启动（推荐）**

```bash
启动全部.bat
```

**方式二：分别启动**

```bash
# 终端 1 - 启动后端
python -m agent.server

# 终端 2 - 启动前端
cd web
npm install   # 首次运行需要
npm run dev
```

### 4. 访问

- 前端界面：http://localhost:3000
- 后端 API：http://127.0.0.1:5001
- API 文档：http://127.0.0.1:5001/docs

---

## 添加新 Skill

将新技能放到 `skills/` 目录下：

```
skills/
└── my-new-skill/
    ├── SKILL.md           # 技能描述（LLM 据此理解何时调用）
    └── agent.py           # 执行逻辑 + TOOLS 定义
```

SKILL.md 文件头格式：

```markdown
---
name: my-new-skill
description: 简短描述，触发词
---

# 我的新技能

当用户请求 XXX 时，立即使用此 skill。
```

agent.py 中必须定义 `TOOLS` 列表，供 LLM 动态调用。

---

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查，查看已加载 Skills |
| `/api/agent/skills` | GET | 列出所有可用 Skills |
| `/api/agent/chat` | POST | 对话（支持文件上传） |
| `/api/agent/chat/stream` | POST | 流式对话（实时输出） |
| `/download?file=xxx` | GET | 下载生成的文件 |

---

## 技术选型

| 组件 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph（已安装）/ 纯 Python（未安装） | 自动降级 |
| LLM | 阿里云 DashScope (qwen-turbo) | OpenAI 兼容 API |
| 后端服务 | FastAPI + Uvicorn | 高性能异步 API |
| 前端 | Nuxt 3 + Vue 3 | SSR + SPA 双模式 |
| 工具注册 | 动态加载 agent.py 的 TOOLS | 按需加载 |
