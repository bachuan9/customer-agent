# 电商智能客服 Agent

这是一个基于 FastAPI、SQLite 和原生前端工作台的电商客服 Agent 项目。项目用于练习客服业务系统、Python 后端、SQL 数据库、FastAPI 接口、RAG 知识库、LLM Function Calling、权限控制和工具调用日志。

## 核心能力

- 订单：创建、列表、查询、更新状态。
- 物流：创建、列表、查询、更新状态。
- 投诉工单：创建、列表、筛选、详情、状态流转、优先级、处理人分配、跟进状态和原因提醒、需要跟进队列和统计。
- 投诉备注：添加、查看、修改、删除。
- 知识库/RAG：支持 Markdown 知识库和数据库知识库，Agent 可检索客服政策并展示命中原因。
- RAG 工程化：支持知识切片、embedding provider、混合检索、索引重建、RAG Trace 和轻量评测集。
- LLM Agent：支持 DeepSeek Function Calling 选择工具，并支持订单、物流、知识库多工具协作和客服处理建议。
- 多轮上下文：基于 session memory 记住最近订单号/物流号，支持“查订单 A101”后继续追问“那物流呢”。
- Agent Trace：结构化展示并持久化回看意图识别、执行模式、工具选择、工具参数、工具结果、RAG 命中依据、人工确认要求和 LLM 降级原因。
- Agent 评测：提供自动化评测集，覆盖意图识别、工具调用、RAG 命中、多轮上下文和组合工具链路。
- LangGraph 工作流：支持订单工具、物流工具、RAG 工具的多工具编排，并在前端展示节点执行流水线。
- 主客服窗口接入 LangGraph：`/chat` 中的订单/物流高风险问题会调用 LangGraph 状态机，返回节点流程和决策解释。
- 人工确认：写操作先进入待确认状态，用户确认后才执行。
- 智能优先级：订单/物流异常确认创建投诉时自动标记高优先级，并分配给客服主管。
- 主管队列：支持一键查看客服主管处理中高优先级投诉，并在首页展示待处理数量。
- 主管接单：支持一键把投诉分配给客服主管并改为处理中。
- RBAC 权限：普通客服和主管权限不同。
- 用户管理：主管可以查看用户、新增用户、修改用户角色。
- 审计日志：记录登录、用户管理、知识库维护等后台操作。
- 工具日志：记录工具来源、参数、结果、失败原因，支持筛选和查看详情。
- 自动测试：使用 pytest 覆盖 API、数据库、Agent、RAG 等核心链路。

## 项目链路

```text
web/app.js
-> app/api/routes.py
-> app/services/agent.py
-> app/services/llm_agent.py
-> app/services/llm_client.py
-> DeepSeek
-> app/services/tool_registry.py
-> app/services/tools.py
-> app/storage/db.py
-> app/services/llm_reply.py
-> web/app.js
```

## Agent / RAG 架构

```text
用户输入
-> FastAPI /chat
-> Agent 意图识别
-> LLM Function Calling 或规则兜底
-> tool_registry 选择并执行工具
-> tools.py 组合订单、物流、投诉、知识库能力
-> SQLite 持久化业务数据、会话记忆、工具日志
-> RAG 检索知识 chunk，并计算关键词分数和 embedding 分数
-> llm_reply 基于工具结果或 RAG 命中内容生成自然客服回复
-> Agent Trace 返回前端展示执行过程
```

工程化能力：

```text
Session Memory：保存最近订单号/物流号，支持多轮上下文补全。
RAG Evaluation：验证知识库检索是否命中预期来源。
Agent Evaluation：验证意图识别、工具调用、RAG、多轮上下文和组合工具链路。
Trace Observability：展示执行模式、工具参数、RAG 分数、回复来源和降级原因。
Fallback：LLM 工具选择或回复生成失败时，自动退回规则 Agent 或模板回复。
```

写操作会多一层安全确认：

```text
LLM 建议写工具
-> 后端保存 pending_llm_action
-> 用户回复“确认执行”
-> RBAC 权限检查
-> call_tool(...)
-> SQLite 更新数据
-> 工具日志记录
```

## LangGraph 多工具工作流

LangGraph 最初作为实验区用于演示更清晰的 Agent 状态机流程，现在也已小范围接入主客服窗口：

```text
/chat
-> 订单/物流高风险问题
-> run_langgraph_agent(...)
-> 返回 LangGraph 节点流程、决策解释和确认结果
```

独立实验区仍然可以直接测试完整流程：

```text
用户输入
-> /langgraph/agent
-> check_pending_confirmation：检查上一轮是否有待确认动作
-> select_tool：根据订单号、物流号或 LLM/RAG 选择工具
-> call_tool：调用订单组合工具、物流组合工具或 RAG 知识库工具
-> summarize_decision：整理工具选择原因、业务证据和下一步建议
-> assess_risk：结合用户文本和工具结果判断风险
-> confirm_complaint：高风险时保存 pending action，等待用户确认
-> create_complaint：用户确认后写入投诉工单
```

原始实验区流程：

```text
用户输入
-> /langgraph/agent
-> check_pending_confirmation：检查上一轮是否有待确认动作
-> select_tool：根据订单号、物流号或 LLM/RAG 选择工具
-> call_tool：调用订单组合工具、物流组合工具或 RAG 知识库工具
-> assess_risk：结合用户文本和工具结果判断风险
-> confirm_complaint：高风险时保存 pending action，等待用户确认
-> create_complaint：用户确认后写入投诉工单
```

工具选择策略：

```text
输入包含 A101 这类订单号：调用 handle_order_issue
输入包含 L101 这类物流号：调用 handle_logistics_issue
没有明确业务编号：调用 search_knowledge / RAG
```

前端工作台会展示：

```text
节点执行流水线
选择的工具
工具参数
风险等级
是否等待确认
工具结构化结果
创建后的投诉编号
```

这部分适合面试时重点说明：

```text
项目不是简单聊天机器人，而是用 LangGraph 把“工具选择、工具调用、决策解释、风险判断、用户确认、数据库写入”拆成可观察的节点工作流，并把订单/物流高风险场景接入了主客服窗口。
```

## 快速开始

### 方式一：Docker 启动（推荐）

如果你只是想运行项目、测试网页和接口，推荐使用 Docker。它会固定 Python 版本、依赖和启动命令，避免本机环境差异。

复制配置文件：

```powershell
Copy-Item .env.example .env
```

启动或重新构建后启动：

```powershell
docker compose up --build -d
```

查看服务是否正常：

```powershell
docker ps
```

如果你修改了后端或前端代码，需要重新执行：

```powershell
docker compose up --build -d
```

访问地址：

```text
网页工作台：http://127.0.0.1:8001/web
接口文档：http://127.0.0.1:8001/docs
健康检查：http://127.0.0.1:8001/health
```

健康检查正常时会返回：

```json
{"status":"ok"}
```

停止 Docker 服务：

```powershell
docker compose down
```

### 方式二：本地开发启动

如果你要边改代码边调试，可以用本地 Python 启动。注意：如果 Docker 已经占用 `8001`，需要先执行 `docker compose down`，否则端口会冲突。

创建并激活 Python 3.11 虚拟环境：

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1
```

安装依赖：

```powershell
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt
```

本地启动后端：

```powershell
.\.venv311\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir . --port 8001
```

## 默认账号

```text
普通客服：agent1 / agent123
主管：manager1 / manager123
```

普通客服可以处理日常查询；主管可以执行知识库维护、用户管理、部分写操作确认。

## LLM 配置

默认可以关闭 LLM，只使用本地规则 Agent：

```env
LLM_ENABLED=false
```

如需启用 DeepSeek：

```env
LLM_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT_SECONDS=60
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=你的真实key
```

注意：`.env` 已被 `.gitignore` 忽略，不要提交真实 API Key。

## 常用测试命令

运行全部自动测试：

```powershell
.\.venv311\Scripts\python.exe -m pytest -q
```

如果本机启用了真实 LLM，完整测试可能因为网络请求或模型超时变慢。可以先跑主线核心测试，确认项目主链路正常：

```powershell
.\.venv311\Scripts\python.exe -m pytest tests\test_db_layer.py tests\test_api_routes.py tests\test_agent_core.py tests\test_langgraph_agent.py -q
.\.venv311\Scripts\python.exe -m pytest tests\test_langchain_agent.py tests\test_langchain_rag_agent.py tests\test_langchain_retriever.py tests\test_langchain_tools.py tests\test_knowledge_rag.py -q
.\.venv311\Scripts\python.exe -m pytest tests\test_agent_evaluation.py -q
```

检查前端 JavaScript 语法：

```powershell
node --check web\app.js
```

检查 Python 文件能否编译：

```powershell
.\.venv311\Scripts\python.exe -m compileall app scripts
```

当前完整检查应看到：

```text
pytest: 147 passed
node --check web/app.js: passed
python -m compileall app scripts: passed
```

## 手动测试建议

打开 `http://127.0.0.1:8001/web` 后，可以按这个顺序测试：

```text
1. 登录 agent1，测试订单、物流、投诉查询。
2. 登录 manager1，测试知识库新增/修改/删除。
3. 登录 manager1，测试用户管理：新增用户、修改角色、禁用/启用用户、重置密码。
4. 切换到普通客服账号，确认不能维护知识库和用户管理。
5. 测试写操作：输入“更新订单 A101 shipped”，再确认执行。
6. 点击工具日志，查看 LLM Agent、权限拒绝、确认执行等记录。
7. 点击审计日志，查看并筛选登录、用户管理、知识库维护等后台操作记录。
8. 在知识库里新增一条政策，再用聊天框测试 RAG 检索。
9. 点击会话列表，测试待回复状态和人工客服回复。
10. 在 LangGraph 实验区点击“订单超时”，查看节点流水线和订单工具调用。
11. 在 LangGraph 实验区点击“确认创建投诉”，确认投诉工单被创建并返回投诉编号。
```

## 主要目录

```text
app/api/routes.py：FastAPI 路由入口
app/models/schemas.py：请求和响应数据格式
app/services/agent.py：聊天业务总调度
app/services/llm_agent.py：LLM 工具选择
app/services/llm_client.py：DeepSeek API 通信
app/services/llm_reply.py：LLM 最终回复生成
app/services/tool_registry.py：工具注册、调用和日志入口
app/services/tools.py：业务工具函数
app/storage/db.py：SQLite 数据库访问层
web/：前端客服工作台
tests/：pytest 自动测试
docs/：开发文档、设计文档、RAG 知识库
practice/：个人学习笔记，不提交到公开仓库
```

## 提交注意事项

不要提交：

```text
.env
data/*.db
logs/*.log
practice/
```

提交前建议运行：

```powershell
git status --short
.\.venv311\Scripts\python.exe -m pytest -q
node --check web\app.js
.\.venv311\Scripts\python.exe -m compileall app scripts
```

更多启动、测试和排错步骤见 [运行与测试手册](docs/运行与测试手册.md) 和 [开发手册](docs/development-guide.md)。

Docker 部署和容器启动步骤见 [部署手册](docs/部署手册.md)。
