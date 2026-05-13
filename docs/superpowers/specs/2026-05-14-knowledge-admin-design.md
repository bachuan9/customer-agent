# 知识库管理后台设计

## 1. 目标

把当前只能靠 Markdown 文件维护的知识库，升级成可以通过接口和前端页面管理的知识库。

第一版重点不是做复杂 RAG，而是让你理解这条项目链路：

```text
前端表单
-> FastAPI 接口
-> db.py SQL
-> SQLite 知识库表
-> search_knowledge 检索
-> Agent 回复
```

## 2. 当前问题

现在知识库主要来自：

```text
docs/knowledge/*.md
```

这种方式适合开发阶段，但不适合真实客服系统。

原因是：

```text
客服或运营不能直接在网页里新增规则
每次改知识库都像在改代码
Agent 不能方便地使用最新运营规则
```

## 3. 第一版功能范围

本次只做一个新手友好的版本：

```text
查看知识库列表
新增知识库
修改知识库
删除知识库
让 search_knowledge 同时检索数据库知识库
在前端增加知识库管理区域
```

暂时不做：

```text
向量数据库
LangChain
复杂分词
真实登录鉴权
富文本编辑器
知识库分类权限
```

## 4. 数据库设计

新增表：

```sql
CREATE TABLE IF NOT EXISTS knowledge_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT DEFAULT NULL
)
```

字段含义：

```text
id：数据库自增 ID
title：知识标题，比如“退款多久到账”
content：知识内容，Agent 真正检索和引用的文本
tags：标签，比如 refund, shipping，第一版先用普通字符串
enabled：是否启用，1 表示启用，0 表示停用
created_at：创建时间
updated_at：更新时间
```

## 5. 后端接口设计

新增接口：

```text
GET /knowledge
查看知识库列表

POST /knowledge
新增知识库

PATCH /knowledge/{article_id}
修改知识库

DELETE /knowledge/{article_id}
删除知识库
```

这些接口主要服务前端管理页面。

Agent 检索仍然走现有工具：

```text
search_knowledge(query)
```

这样前端管理和 Agent 使用可以分开：

```text
管理接口负责维护知识
search_knowledge 负责给 Agent 查知识
```

## 6. 代码分层

本次会涉及这些文件：

```text
app/storage/db.py
负责建表和 SQL 增删改查

app/models/schemas.py
定义新增/修改知识库时的请求格式

app/api/routes.py
提供 /knowledge 相关接口

app/services/tools.py
让 search_knowledge 同时检索 Markdown 文件和数据库知识库

web/index.html
增加知识库管理区域

web/app.js
处理新增、修改、删除、刷新列表

web/styles.css
补充知识库管理区域样式

tests/
补充知识库接口和 search_knowledge 测试
```

## 7. search_knowledge 的设计

第一版保留现有 Markdown 检索，同时增加数据库检索。

流程：

```text
读取 docs/knowledge/*.md
-> 读取 knowledge_articles 表里 enabled=1 的内容
-> 用当前简单关键词匹配逻辑查找
-> 合并匹配结果
-> 返回给 Agent
```

这样做的好处：

```text
不会破坏现有知识库
旧 Markdown 仍然可用
新建的数据库知识库也能被 Agent 用到
```

## 8. 前端设计

在现有客服工作台里增加一个知识库管理区。

第一版包含：

```text
标题输入框
标签输入框
内容输入框
新增按钮
知识库列表
编辑按钮
删除按钮
刷新按钮
```

为了保持学习清晰，第一版不做复杂弹窗，直接用表单完成新增和修改。

## 9. 错误处理

需要处理：

```text
标题为空：返回 400
内容为空：返回 400
修改不存在的知识：返回 404
删除不存在的知识：返回 404
数据库异常：由测试及时发现，第一版不额外包装复杂错误
```

## 10. 测试计划

后端测试：

```text
新增知识库成功
列表能看到新增内容
修改知识库成功
删除知识库成功
search_knowledge 能检索到数据库知识库内容
```

基础检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check web\app.js
.\.venv\Scripts\python.exe -m compileall app
```

## 11. 学习重点

这一步你要重点理解：

```text
数据库表为什么这样设计
routes.py 为什么不直接写 SQL
db.py 为什么负责 SQL
schemas.py 为什么定义请求格式
search_knowledge 为什么要同时查 Markdown 和数据库
前端按钮怎么变成后端接口请求
```

一句话总结：

```text
这一步是在把“写死的知识文件”，升级成“可以被页面维护、可以被 Agent 检索的知识库数据”。
```
