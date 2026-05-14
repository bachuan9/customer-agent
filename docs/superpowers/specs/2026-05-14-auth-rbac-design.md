# 教学版登录和真实角色权限设计

## 1. 目标

把当前“前端下拉框选择角色”的方式，升级成“用户登录后，由后端识别用户角色”。

当前问题：

```text
前端可以随便传 role=manager
后端会相信这个 role
这不是真实权限系统
```

目标效果：

```text
用户先登录
-> 后端校验账号密码
-> 后端生成 token
-> 前端后续请求带 token
-> 后端根据 token 找到用户和角色
-> RBAC 使用后端识别出的角色
```

## 2. 第一版范围

本次做教学版，不做企业复杂认证。

包含：

```text
users 表
初始化测试账号
POST /auth/login 登录接口
GET /auth/me 当前用户接口
前端登录面板
前端保存 token
/chat 优先使用 token 识别 user_id 和 role
```

测试账号：

```text
agent1 / agent123 / 普通客服
manager1 / manager123 / 主管
```

暂时不做：

```text
注册
密码找回
邮箱验证
刷新 token
JWT
OAuth
多端登录管理
复杂权限菜单
```

## 3. 数据库设计

新增表：

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    token TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT DEFAULT NULL
)
```

字段含义：

```text
username：登录名
password_hash：密码哈希，不存明文密码
display_name：客服展示名
role：agent 或 manager
token：教学版登录 token
created_at：创建时间
updated_at：更新时间
```

## 4. Token 设计

第一版使用 Python 标准库生成随机 token：

```text
secrets.token_urlsafe(32)
```

登录成功后：

```text
生成 token
保存到 users.token
返回给前端
```

前端后续请求加请求头：

```text
Authorization: Bearer <token>
```

后端根据 token 查 users 表。

说明：

```text
这是教学版 token，适合学习登录主链路。
生产系统通常会用 JWT 或服务端 session，并考虑过期时间、刷新和撤销。
```

## 5. 接口设计

新增：

```text
POST /auth/login
登录，返回 token 和用户信息

GET /auth/me
根据 token 返回当前用户
```

修改：

```text
POST /chat
如果请求头有 Authorization token，就用 token 中的 user_id 和 role。
如果没有 token，先保留兼容旧测试的 req.user_id 和 req.role。
```

为什么保留兼容：

```text
当前测试和部分学习流程还在直接 POST /chat。
第一版先平滑升级，不一次性打断所有旧链路。
```

## 6. 前端设计

左侧会话信息区增加登录表单：

```text
账号
密码
登录按钮
退出按钮
当前登录用户
```

登录成功后：

```text
保存 token 到 localStorage
显示用户 display_name 和 role
后续 /chat 请求带 Authorization 头
```

角色下拉框第一版保留但弱化：

```text
未登录时可用于教学和兼容
已登录时以后端返回角色为准
```

## 7. 安全边界

这一步会提升安全性，但仍然是教学版。

提升点：

```text
不再完全相信前端 role
密码不明文存储
写操作确认时可以使用后端识别角色
```

仍未覆盖：

```text
token 过期
token 刷新
HTTPS
暴力破解限制
细粒度接口权限
```

## 8. 测试计划

新增测试：

```text
默认用户初始化成功
agent1 登录成功
错误密码登录失败
/auth/me 能根据 token 返回用户
/chat 带 manager token 时使用 manager 角色
/chat 带 agent token 时仍会被 RBAC 拦截写操作
```

检查命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check web\app.js
.\.venv\Scripts\python.exe -m compileall app
```

## 9. 学习重点

```text
身份认证 authentication：你是谁
权限控制 authorization：你能做什么
token：登录后的临时通行证
密码哈希：不存明文密码
后端角色：不要相信前端随便传来的 role
```

一句话总结：

```text
登录解决“你是谁”，RBAC 解决“你能不能做这件事”。
```
