# 电商智能客服 Agent

这是一个基于 FastAPI、SQLite 和前端工作台的电商客服 Agent 项目。

项目支持订单查询、物流查询、投诉工单处理、客服备注、LLM Function Calling、写操作人工确认、RBAC 权限控制、工具调用日志和自动化测试。

## 核心能力

- 订单：创建、列表、查询、更新状态。
- 物流：创建、列表、查询、更新状态。
- 投诉：创建、列表、筛选、详情、状态流转、优先级、处理人分配。
- 备注：添加、查看、修改、删除投诉备注。
- Agent：支持规则 Agent 和 LLM Agent。
- LLM：DeepSeek Function Calling 选工具，第二次 LLM 生成自然客服回复。
- RAG：支持从多份本地知识库检索退货、售后、物流、会员等政策。
- 安全：写操作先暂存 `pending_llm_action`，用户确认后才执行。
- 权限：基于 `role` 的轻量 RBAC，普通客服和主管权限不同。
- 日志：记录工具来源、参数、结果、失败原因，支持可观测性摘要。
- 测试：pytest 覆盖核心函数、API 接口、数据库层。

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

写操作会多一段安全流程：

```text
LLM 建议写工具
-> 后端拦截并保存 pending_llm_action
-> 用户回复“确认执行”
-> RBAC 权限检查
-> call_tool(...)
-> SQLite 更新数据
-> 工具日志记录
```

## 快速开始

创建并激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
pip install -r requirements.txt
```

复制配置文件：

```powershell
Copy-Item .env.example .env
```

启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir . --port 8001
```

演示或部署时，不建议使用 `--reload`，可参考 [开发手册](docs/development-guide.md) 的“演示/生产启动”。

访问：

```text
网页工作台：http://127.0.0.1:8001/web
接口文档：http://127.0.0.1:8001/docs
健康检查：http://127.0.0.1:8001/health
```

## LLM 配置

默认 `.env.example` 里关闭 LLM：

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

## 部署准备提示

部署或演示前建议确认：

```text
.env 已创建，并且没有提交真实 API Key
APP_DB_PATH 指向正确的 SQLite 数据库文件
LLM_ENABLED 根据环境明确设置 true 或 false
pytest 测试通过
健康检查 /health 正常
工具日志可查看
```

更多命令和排错步骤见：[docs/development-guide.md](docs/development-guide.md)

## 测试

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前测试覆盖：

```text
LLM tool_call 解析
RBAC 权限规则
权限拒绝日志
主管确认执行
FastAPI 接口
数据库订单与日志统计
RAG 知识库检索
```

测试使用临时 SQLite 数据库，不会污染 `data/complaints.db`。

## 主要目录

```text
app/api/routes.py：FastAPI 路由层
app/models/schemas.py：请求和响应数据格式
app/services/agent.py：聊天业务总调度
app/services/llm_agent.py：LLM 工具选择层
app/services/llm_client.py：LLM API 通信层
app/services/llm_reply.py：LLM 最终回复层
app/services/tool_registry.py：工具注册、调用和日志入口
app/services/tools.py：业务工具函数
app/storage/db.py：SQLite 数据库访问层
web/：前端客服工作台
tests/：pytest 自动化测试
docs/：设计文档和开发资料
docs/knowledge/：RAG 知识库，支持多个 Markdown 文件
```

## 开发文档

更多命令和排错步骤见：

```text
docs/development-guide.md
```

本地学习笔记位于 `practice/`，属于个人学习资料，不随公开仓库上传。
