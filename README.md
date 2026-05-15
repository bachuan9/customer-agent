# 电商智能客服 Agent

这是一个基于 FastAPI、SQLite 和原生前端工作台的电商客服 Agent 项目。项目用于练习客服业务系统、Python 后端、SQL 数据库、FastAPI 接口、RAG 知识库、LLM Function Calling、权限控制和工具调用日志。

## 核心能力

- 订单：创建、列表、查询、更新状态。
- 物流：创建、列表、查询、更新状态。
- 投诉工单：创建、列表、筛选、详情、状态流转、优先级、处理人分配。
- 投诉备注：添加、查看、修改、删除。
- 知识库/RAG：支持 Markdown 知识库和数据库知识库，Agent 可检索客服政策。
- LLM Agent：支持 DeepSeek Function Calling 选择工具。
- 人工确认：写操作先进入待确认状态，用户确认后才执行。
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
.\.venv\Scripts\python.exe -m pytest -q
```

检查前端 JavaScript 语法：

```powershell
node --check web\app.js
```

检查 Python 文件能否编译：

```powershell
.\.venv\Scripts\python.exe -m compileall app
```

当前完整检查应看到：

```text
pytest: 49 passed
node --check web/app.js: passed
python -m compileall app: passed
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
.\.venv\Scripts\python.exe -m pytest -q
node --check web\app.js
.\.venv\Scripts\python.exe -m compileall app
```

更多启动、测试和排错步骤见 [开发手册](docs/development-guide.md)。
