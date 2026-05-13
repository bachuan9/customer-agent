# 开发手册

这份文档记录本项目的常用开发命令、配置方式、测试方式和排错步骤。

## 1. 环境准备

推荐使用 Python 3.8+。

创建虚拟环境：

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
pip install -r requirements.txt
```

如果不想激活虚拟环境，也可以直接使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. 配置 .env

复制模板：

```powershell
Copy-Item .env.example .env
```

默认配置：

```env
APP_DB_PATH=data/complaints.db
LLM_ENABLED=false
DEEPSEEK_API_KEY=
```

默认关闭 LLM 的原因：

```text
没有 API Key 或网络失败时，不影响规则 Agent 和本地功能。
```

启用 DeepSeek：

```env
LLM_ENABLED=true
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
LLM_TIMEOUT_SECONDS=60
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=你的真实key
```

注意：

```text
.env 里有真实 API Key，不要提交。
.env.example 只放模板，可以提交。
```

`APP_DB_PATH` 用来指定 SQLite 数据库文件位置。

开发环境可以使用：

```env
APP_DB_PATH=data/complaints.db
```

测试环境会通过 pytest 临时设置自己的数据库路径，避免污染真实数据。

## 3. 启动后端

开发启动命令：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir . --port 8001
```

`--reload` 的作用是：

```text
开发时改代码，服务自动重启。
```

演示/生产启动命令：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --app-dir .
```

演示/生产时不建议加 `--reload`，因为它更适合开发调试，不适合稳定运行。

访问地址：

```text
http://127.0.0.1:8001/web
http://127.0.0.1:8001/docs
http://127.0.0.1:8001/health
```

健康检查正常返回：

```json
{"status":"ok"}
```

## 4. 环境变量清单

当前 `.env` 支持：

```text
APP_NAME：应用名称
APP_ENV：运行环境，例如 dev / prod
APP_DB_PATH：SQLite 数据库文件路径
LLM_ENABLED：是否启用 LLM
LLM_PROVIDER：LLM 服务商，目前是 deepseek
LLM_MODEL：模型名称
LLM_TIMEOUT_SECONDS：LLM 请求超时时间
DEEPSEEK_BASE_URL：DeepSeek API 地址
DEEPSEEK_API_KEY：DeepSeek API Key
```

开发环境建议：

```env
APP_ENV=dev
APP_DB_PATH=data/complaints.db
LLM_ENABLED=false
```

演示环境如果要展示真实 LLM：

```env
APP_ENV=demo
APP_DB_PATH=data/complaints.db
LLM_ENABLED=true
LLM_TIMEOUT_SECONDS=60
DEEPSEEK_API_KEY=你的真实key
```

生产或正式演示前，至少检查：

```text
.env 是否存在
DEEPSEEK_API_KEY 是否没有写进代码或 README
APP_DB_PATH 是否指向你想使用的数据库
LLM_ENABLED 是否符合本次演示目标
```

## 5. 常用手动测试

网页打开：

```text
http://127.0.0.1:8001/web
```

查询类：

```text
查订单 A101
查物流 L101
查看投诉
查看投诉 C-0001
7 天后还能退货吗
质量问题退货运费谁承担
物流超过48小时没有更新怎么办
会员积分退款后会扣回吗
```

LLM 写操作安全确认：

```text
把订单 A101 改成 delivered
确认执行
```

RBAC 权限测试：

```text
普通客服确认 update_order：应该被拒绝
主管确认 update_order：应该成功
```

工具日志检查：

```text
点击“工具日志”
查看来源统计和最新日志
```

常见来源：

```text
LLM Agent：LLM 选工具
LLM 确认执行：人工确认后执行
权限拒绝：RBAC 拒绝
规则 Agent：旧规则逻辑
历史未知：老日志
```

## 6. 自动化测试

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前测试分三类：

```text
tests/test_agent_core.py：核心函数和权限确认
tests/test_api_routes.py：FastAPI 接口
tests/test_db_layer.py：数据库层
tests/test_knowledge_rag.py：最小 RAG 知识库检索
```

RAG 知识库目录：

```text
docs/knowledge/return-policy.md
docs/knowledge/shipping-policy.md
docs/knowledge/membership-policy.md
```

新增知识库时，把 Markdown 文件放进 `docs/knowledge/`，`search_knowledge` 会自动遍历 `.md` 文件。

测试数据库隔离：

```text
测试使用临时 SQLite，不会污染 data/complaints.db。
```

相关文件：

```text
pytest.ini
tests/conftest.py
```

## 7. 常用接口

```text
GET  /health
POST /chat
GET  /orders
GET  /orders/{order_no}
PATCH /orders/{order_no}
GET  /logistics
GET  /logistics/{tracking_no}
PATCH /logistics/{tracking_no}
GET  /complaints
GET  /complaints/{complaint_id}
PATCH /complaints/{complaint_id}
GET  /tool-logs
GET  /tool-logs/stats
GET  /tools/function-calling
```

## 8. 关键文件职责

```text
routes.py：HTTP 接口入口
schemas.py：请求和响应格式
agent.py：聊天业务总调度
llm_agent.py：LLM 选工具
llm_client.py：调用 DeepSeek
llm_reply.py：生成自然回复
tool_registry.py：工具总台和日志入口
tools.py：业务工具函数
db.py：SQLite 数据库操作
web/app.js：前端交互和 fetch 请求
```

## 9. 部署/演示前检查清单

演示前建议按顺序做：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

确认看到：

```text
14 passed
```

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --app-dir .
```

检查：

```text
http://127.0.0.1:8001/health
http://127.0.0.1:8001/web
http://127.0.0.1:8001/docs
```

网页手动测试：

```text
查订单 A101
查物流 L101
把订单 A101 改成 delivered
普通客服确认执行：应被拒绝
主管确认执行：应成功
点击工具日志：应看到来源统计
```

## 10. SQLite 数据库备份

当前项目使用 SQLite，默认数据库路径：

```text
data/complaints.db
```

演示前可以复制一份备份：

```powershell
Copy-Item data\complaints.db data\complaints.backup.db
```

如果演示过程中数据被改乱，可以停止后端后恢复：

```powershell
Copy-Item data\complaints.backup.db data\complaints.db -Force
```

注意：

```text
恢复数据库前先停止后端，避免服务正在写数据库。
```

## 11. 日志和可观测性检查

前端点击：

```text
工具日志
```

重点看：

```text
来源统计
失败类型
最新调用工具
参数
错误原因
```

常见来源含义：

```text
LLM Agent：LLM 选工具
LLM 确认执行：人工确认后执行
权限拒绝：RBAC 拒绝
规则 Agent：旧规则逻辑
历史未知：旧日志
```

如果 LLM 没反应，先看：

```text
后端终端 debug 日志
工具日志最新来源
.env 里的 LLM_ENABLED 和 DEEPSEEK_API_KEY
```

## 12. 常见问题

### /health 正常，但 /web 打不开

确认启动命令使用了项目根目录：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir . --port 8001
```

然后访问：

```text
http://127.0.0.1:8001/web
```

### LLM 没有调用

检查 `.env`：

```env
LLM_ENABLED=true
DEEPSEEK_API_KEY=你的真实key
```

重启后端。

然后看后端终端是否出现：

```text
[DEBUG] LLM selected tool: ...
```

也可以点前端“工具日志”，看最新来源是否是：

```text
LLM Agent
```

### LLM 超时

可以把 `.env` 里超时时间调大：

```env
LLM_TIMEOUT_SECONDS=60
```

如果仍然超时，系统会 fallback 到规则 Agent。

### 普通客服确认执行被拒绝

这是正常的 RBAC 行为。

切换角色为：

```text
主管
```

再输入：

```text
确认执行
```

### pytest 收集到 scripts 里的文件

项目已经有：

```text
pytest.ini
```

它限制 pytest 只收集：

```text
tests/
```

如果还是异常，确认当前命令是在项目根目录运行。

## 13. 推荐开发顺序

每次改代码建议按这个顺序：

```text
1. 明确要改哪一层
2. 小步修改
3. 运行 pytest
4. 启动后端手动测试
5. 看工具日志确认链路
6. 更新学习文档或 README
```

一句话总结：

```text
先让功能可用，再让安全可控，最后让系统可测试、可观察、可维护。
```
