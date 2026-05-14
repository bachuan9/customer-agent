# 用户管理第一版设计

## 1. 目标

在已有登录系统基础上，增加一个最小用户管理能力。

第一版目标：

```text
主管可以查看用户列表
主管可以新增用户
主管可以修改用户角色
```

## 2. 功能范围

新增接口：

```text
GET /users
查看用户列表，必须 manager

POST /users
新增用户，必须 manager

PATCH /users/{username}/role
修改用户角色，必须 manager
```

第一版暂时不做：

```text
删除用户
禁用用户
修改密码
重置 token
分页搜索
```

## 3. 角色范围

当前只允许：

```text
agent
manager
```

原因：

```text
项目目前只有普通客服和主管两种权限模型。
先保持简单，避免引入 admin 等新概念。
```

## 4. 后端分层

数据库层：

```text
app/storage/db.py
fetch_users()
update_user_role(...)
insert_user(...)
```

接口层：

```text
app/api/routes.py
GET /users
POST /users
PATCH /users/{username}/role
```

权限：

```text
所有用户管理写/读接口都必须 require_manager(...)
```

原因：

```text
用户和角色属于高风险配置，不能给普通客服维护。
```

## 5. 前端设计

在客服工作台增加“用户管理”区域。

第一版包含：

```text
用户列表
新增用户表单
修改角色按钮
刷新用户按钮
```

非主管状态：

```text
显示权限提示
禁用新增按钮和修改角色按钮
```

主管状态：

```text
允许新增用户
允许修改角色
```

## 6. 数据流

查看用户：

```text
前端点击用户管理
-> GET /users
-> require_manager
-> fetch_users()
-> 返回用户列表
```

新增用户：

```text
前端提交表单
-> POST /users
-> require_manager
-> insert_user(...)
-> 密码哈希保存
-> 返回用户信息
```

修改角色：

```text
点击角色按钮
-> PATCH /users/{username}/role
-> require_manager
-> update_user_role(...)
-> 返回更新后的用户
```

## 7. 错误处理

```text
未登录：401
非主管：403
用户名重复：409
角色非法：400
用户不存在：404
```

## 8. 测试计划

```text
manager 可以查看用户列表
agent 不能查看用户列表
manager 可以新增用户
重复 username 返回 409
非法 role 返回 400
manager 可以修改用户角色
不存在用户返回 404
```

## 9. 学习重点

```text
用户管理为什么必须走后端权限
新增用户为什么要哈希密码
修改角色为什么是高风险操作
接口权限如何复用 require_manager
```

一句话总结：

```text
用户管理是权限系统的管理入口，必须由后端严格保护。
```
