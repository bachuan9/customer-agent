# 开发手册

这份文档记录本项目的本地启动、功能测试、自动测试、排错和提交前检查流程。它的目标是让你每次重新打开项目时，都能照着步骤把系统跑起来。

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

开发环境推荐配置：

```env
APP_ENV=dev
APP_DB_PATH=data/complaints.db
LLM_ENABLED=false
```

启用 DeepSeek 时：

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
APP_DB_PATH 用来指定 SQLite 数据库文件位置。
```

## 3. 启动后端

开发启动命令：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir . --port 8001
```

`--reload` 的作用：

```text
开发时修改代码，服务会自动重启。
```

演示或稳定运行时，可以不加 `--reload`：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --app-dir .
```

访问地址：

```text
网页工作台：http://127.0.0.1:8001/web
接口文档：http://127.0.0.1:8001/docs
健康检查：http://127.0.0.1:8001/health
```

健康检查正常返回：

```json
{"status":"ok"}
```

## 4. 默认账号

系统启动时会自动创建两个教学账号：

```text
普通客服：agent1 / agent123
主管：manager1 / manager123
```

权限差异：

```text
普通客服：适合测试日常查询、普通客服对话。
主管：可以维护知识库、管理用户、执行需要更高权限的确认操作。
```

## 5. 常用手动测试

打开：

```text
http://127.0.0.1:8001/web
```

建议按这个顺序测试。

### 5.1 基础服务

```text
打开 /health，确认返回 {"status":"ok"}。
打开 /docs，确认能看到接口文档。
打开 /web，确认客服工作台能加载。
```

### 5.2 订单和物流

在聊天框输入：

```text
查订单 A101
查物流 L101
我的订单 A101 48小时了，怎么还没发货
```

或者点击左侧：

```text
订单列表
物流列表
```

期望结果：

```text
能看到订单或物流状态。
如果编号不存在，应看到未找到提示。
订单异常场景会同时查询订单状态、关联物流状态和知识库政策。
订单异常和物流异常回复里都会出现“客服处理建议”，用于告诉客服下一步该怎么跟进。
如果用户确认创建异常投诉，系统会自动把投诉优先级设为 high，并分配给“客服主管”，方便优先处理。
确认创建成功后，回复会直接显示投诉编号、优先级和处理人。
点击“主管待处理”可以快速查看 priority=high、handler=客服主管、status=processing 的重点投诉。
首页“主管待处理”统计卡片会展示这类重点工单的当前数量。
投诉列表会展示“跟进状态”和“跟进原因”，用于提示正常、高优先级请尽快处理、需要跟进或已解决，并说明系统为什么这样判断。
点击“需要跟进”可以快速查看 follow_up_status=需要跟进 的投诉队列。
首页“需要跟进”统计卡片会展示这类投诉的当前数量。
```

### 5.3 投诉工单

可以测试：

```text
我要投诉
查看投诉
查看投诉 C-0001
```

在投诉列表里可以测试：

```text
查看详情
分配处理人
分配给客服主管
主管接单
改为处理中
解决投诉
修改优先级
添加备注
查看备注
修改备注
删除备注
```

### 5.4 知识库和 RAG

使用主管账号登录：

```text
manager1 / manager123
```

点击：

```text
知识库
```

测试：

```text
新增一条知识
搜索知识
按标签筛选
编辑知识
删除知识
```

聊天框可测试：

```text
退款多久到账
质量问题退货运费谁承担
会员积分退款后会扣回吗
```

期望结果：

```text
Agent 回复里能参考知识库内容。
```

RAG 调试面板会显示：

```text
score：这条知识和用户问题的相关度分数。
matched_keywords：用户问题和知识内容共同命中的关键词。
matched_groups：命中的业务分类，例如 shipping 表示物流配送。
match_reason：把分数、关键词、分类和来源组织成一句可读解释。
```

### 5.5 聊天历史和会话状态

本项目把“用户能看到的聊天历史”和“Agent 内部状态”分开保存：

```text
chat_messages：真实聊天记录，保存用户消息、Agent 回复和 Agent 执行步骤。
session_messages：Agent 内部记忆，保存 waiting_confirm、pending_update 等流程状态。
```

这样设计的原因是：

```text
聊天历史用于页面展示和回看。
Agent 执行步骤用于回看当时经过了哪些工具、是否调用 LLM、回复来源是什么。
内部状态用于多轮流程控制，不应该直接当成聊天内容展示。
```

手动测试：

```text
1. 打开网页，发送“查订单 A101”。
2. 确认 Agent 回复下方出现“Agent 执行步骤”和“结构化 Trace”。
3. 刷新页面，确认刚才的聊天气泡、Agent 执行步骤和结构化 Trace 仍然显示。
4. 点击“会话列表”，确认能看到当前用户的最近消息、消息数、最后时间和待回复/已回复状态。
5. 点击会话列表里的 user_id，确认能切换并加载该用户聊天历史。
6. 点击会话列表里的“回复”，输入一条人工客服回复并发送。
7. 确认聊天历史里出现刚才的人工回复。
8. 点击“清空聊天”。
9. 再次刷新页面，确认历史不会回来。
```

结构化 Trace 用于调试 Agent 本次执行的关键字段：

```text
intent：识别到的意图
execution_mode：规则 Agent 或 LLM Agent
reply_source：回复来源
LLM选择工具：大模型选择的工具名
是否需要确认：LLM 写操作是否进入人工确认
工具参数：Function Calling 传给工具的参数
工具结果摘要：工具返回结果的摘要
RAG是否命中：知识库是否找到可靠内容
RAG来源：命中的 Markdown 或数据库知识来源
RAG最高分：本次知识检索的最高相关度分数
RAG命中原因：关键词、分类、分数和来源解释
LLM降级原因：LLM 调用失败时的回退原因
```

清空聊天会同时做两件事：

```text
删除 chat_messages 里的聊天历史。
删除 session_messages 里的 Agent 内部待确认状态。
```

权限规则：

```text
未登录：保留教学模式，可以按 user_id 查看和清空历史。
普通客服登录：只能查看和清空自己的历史。
主管登录：可以查看和清空任意用户历史。
```

会话列表：

```text
GET /chat/sessions 会按 user_id 聚合聊天记录。
每条会话会返回 user_id、last_sender、last_message、last_message_at、message_count、needs_reply。
needs_reply 表示这条会话是否需要客服继续回复。
如果最后一条消息是 user，needs_reply 就是 true，前端显示“待回复”。
如果最后一条消息是 agent，needs_reply 就是 false，前端显示“已回复”。
普通客服登录时只能看到自己的会话。
主管登录时可以看到所有会话。
```

人工回复：

```text
POST /chat/history/{user_id}/reply 用来保存客服手动输入的回复。
这个接口不会调用 Agent，也不会调用 LLM。
它只是把客服写的内容作为 sender=agent 的消息写入 chat_messages。
这样“待回复”会话被处理后，最新消息就会变成 agent，前端会显示“已回复”。
```

相关接口：

```text
GET    /chat/sessions
GET    /chat/history/{user_id}
POST   /chat/history/{user_id}/reply
DELETE /chat/history/{user_id}
```

### 5.6 用户管理

使用主管账号登录：

```text
manager1 / manager123
```

点击：

```text
用户管理
```

测试：

```text
查看用户列表
新增普通客服
新增主管
修改某个用户的角色
禁用用户，并确认该用户不能登录
重新启用用户，并确认该用户可以登录
重置用户密码，并确认旧密码失败、新密码成功
```

再切换普通客服登录：

```text
agent1 / agent123
```

期望结果：

```text
普通客服不能管理用户。
后端会返回 403，前端会显示没有权限。
主管可以完成用户管理三类动作：角色调整、启用禁用、重置密码。
```

### 5.6 LLM 写操作确认

如果 `.env` 中 `LLM_ENABLED=true`，可以测试：

```text
把订单 A101 改成 shipped
确认执行
```

权限测试：

```text
普通客服确认写操作：应该被 RBAC 拒绝。
主管确认写操作：应该执行成功。
```

这条链路是：

```text
用户提出修改
-> LLM 选择工具
-> 后端保存 pending_llm_action
-> 用户确认执行
-> RBAC 检查角色
-> 执行工具
-> 写入数据库
-> 记录工具日志
```

### 5.7 工具日志

点击：

```text
工具日志
```

重点看：

```text
来源统计
成功/失败
工具名
参数
错误原因
查看详情
复制参数 JSON
复制结果 JSON
```

常见来源含义：

```text
rule_agent：规则 Agent 调用
llm_agent：LLM 选择工具
llm_confirmed_action：人工确认后执行
rbac_denied：权限拒绝
unknown：旧日志或未知来源
```

### 5.8 审计日志

使用主管账号登录：

```text
manager1 / manager123
```

点击：

```text
审计日志
```

重点看：

```text
谁操作的
做了什么动作
操作对象是谁
成功还是失败
操作时间
按动作 / 结果 / 操作者筛选
```

可以先做几次操作再查看：

```text
登录成功 / 登录失败
新增用户
修改用户角色
禁用 / 启用用户
重置密码
新增 / 修改 / 删除知识库
```

普通客服访问审计日志：

```text
应该被 403 拒绝。
```

## 6. 自动化测试

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前完整测试应看到：

```text
95 passed
```

检查前端 JavaScript：

```powershell
node --check web\app.js
```

检查 Python 编译：

```powershell
.\.venv\Scripts\python.exe -m compileall app
```

推荐提交前完整检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check web\app.js
.\.venv\Scripts\python.exe -m compileall app
```

## 7. 常用接口

```text
GET    /health
POST   /chat
GET    /chat/sessions
GET    /chat/history/{user_id}
POST   /chat/history/{user_id}/reply
DELETE /chat/history/{user_id}

POST   /auth/login
GET    /auth/me
POST   /auth/logout

GET    /orders
POST   /orders
GET    /orders/{order_no}
PATCH  /orders/{order_no}

GET    /logistics
POST   /logistics
GET    /logistics/{tracking_no}
PATCH  /logistics/{tracking_no}

GET    /complaints
GET    /complaints/stats
GET    /complaints/{complaint_id}
PATCH  /complaints/{complaint_id}

POST   /complaints/{complaint_id}/notes
GET    /complaints/{complaint_id}/notes
PATCH  /complaint-notes/{note_id}
DELETE /complaint-notes/{note_id}

GET    /knowledge
GET    /knowledge/{article_id}
POST   /knowledge
PATCH  /knowledge/{article_id}
DELETE /knowledge/{article_id}

GET    /users
POST   /users
PATCH  /users/{username}/role

GET    /tool-logs
GET    /tool-logs/stats
GET    /tools/function-calling
```

## 8. 关键文件职责

```text
app/main.py：FastAPI 应用入口，挂载路由和 web 静态文件。
app/api/routes.py：HTTP 接口入口，接收前端请求。
app/models/schemas.py：请求体和响应体的数据格式。
app/services/agent.py：聊天业务总调度。
app/services/llm_agent.py：LLM Function Calling 工具选择。
app/services/llm_client.py：调用 DeepSeek API。
app/services/llm_reply.py：生成更自然的最终回复。
app/services/tool_registry.py：工具注册、工具调用、工具日志入口。
app/services/tools.py：订单、物流、投诉、知识库等业务工具函数。
app/storage/db.py：SQLite 数据库操作层。
web/index.html：页面结构。
web/app.js：前端交互和 fetch 请求。
web/styles.css：页面样式。
tests/：自动化测试。
docs/knowledge/：Markdown RAG 知识库。
practice/：个人学习笔记，不提交公开仓库。
```

## 9. SQLite 数据库备份

默认数据库：

```text
data/complaints.db
```

演示前可以备份：

```powershell
Copy-Item data\complaints.db data\complaints.backup.db
```

恢复前先停止后端，然后执行：

```powershell
Copy-Item data\complaints.backup.db data\complaints.db -Force
```

为什么要先停止后端：

```text
避免服务正在写数据库时覆盖文件，导致数据异常。
```

## 10. 常见问题排查

### 10.1 /health 正常，但 /web 打不开

确认启动命令包含：

```powershell
--app-dir .
```

推荐命令：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir . --port 8001
```

然后访问：

```text
http://127.0.0.1:8001/web
```

### 10.2 /docs 没有新接口

常见原因：

```text
后端没重启。
启动的不是当前项目目录。
浏览器页面缓存。
代码保存失败。
```

处理方式：

```text
保存代码
重启后端
刷新 /docs
确认终端当前路径是项目根目录
```

### 10.3 登录后仍然没有权限

先确认登录账号：

```text
agent1 是普通客服
manager1 是主管
```

知识库写操作、用户管理等功能需要：

```text
manager
```

如果仍然异常：

```text
退出登录
重新登录 manager1
刷新页面
重新点击功能按钮
```

### 10.4 LLM 没有调用

检查 `.env`：

```env
LLM_ENABLED=true
DEEPSEEK_API_KEY=你的真实key
```

然后重启后端。

也可以查看：

```text
后端终端 debug 日志
前端“工具日志”的最新来源
```

如果来源是 `rule_agent`，说明当前走的是规则 Agent。

如果来源是 `llm_agent`，说明 LLM 已经参与工具选择。

### 10.5 LLM 超时

可以把 `.env` 里的超时时间调大：

```env
LLM_TIMEOUT_SECONDS=60
```

如果仍然超时，系统会回退到规则 Agent，先保证基础功能可用。

### 10.6 普通客服确认执行被拒绝

这是正常的 RBAC 行为。

含义：

```text
普通客服没有权限执行某些写操作。
```

切换到主管后再测试：

```text
manager1 / manager123
```

### 10.7 pytest 收集到不该测试的文件

项目通过 `pytest.ini` 限制 pytest 只收集：

```text
tests/
```

如果仍然异常，确认命令是在项目根目录运行。

## 11. Git 提交前检查

先查看改动：

```powershell
git status --short
```

不要提交：

```text
.env
data/*.db
logs/*.log
practice/
```

提交前建议运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check web\app.js
.\.venv\Scripts\python.exe -m compileall app
```

如果要提交代码但不提交学习文档：

```powershell
git add README.md docs/development-guide.md app web tests
```

不要执行：

```powershell
git add .
```

原因：

```text
git add . 容易把个人学习文档、临时文件一起加进去。
```

## 12. 推荐开发顺序

每次新增功能时，建议按这个顺序：

```text
1. 明确要改哪一层。
2. 先改 db.py，让数据库有能力。
3. 再改 schemas.py，定义请求格式。
4. 再改 routes.py，提供 HTTP 接口。
5. 再改 web/app.js，让前端能调用接口。
6. 补测试。
7. 跑 pytest 和语法检查。
8. 手动测试网页。
9. 更新 README 或开发手册。
```

一句话总结：

```text
先让功能可用，再让权限可控，最后让系统可测试、可观察、可维护。
```
