# 操作审计日志设计

## 背景

项目已有 `tool_call_logs`，用于记录 Agent 或工具调用过程。但后台管理还需要另一类日志：记录“谁在什么时候做了什么管理动作”。

因此新增独立的 `audit_logs`，避免把“工具调用日志”和“人工管理审计”混在一起。

## 第一版范围

记录以下动作：

- 登录成功 / 登录失败
- 退出登录
- 新增用户
- 修改用户角色
- 启用 / 禁用用户
- 重置用户密码
- 知识库新增 / 修改 / 删除

## 数据表

新增表：

```text
audit_logs
```

字段：

```text
id
actor_username
actor_role
action
target_type
target_id
success
detail
created_at
```

## 后端接口

```text
GET /audit-logs
GET /audit-logs/stats
```

权限：

```text
只有 manager 可以查看审计日志。
```

## 前端

左侧增加“审计日志”按钮，点击后在聊天窗口中显示最近审计记录和统计摘要。

## 测试

需要覆盖：

- 登录成功会写审计日志
- 登录失败会写审计日志
- 主管新增用户会写审计日志
- 普通客服不能查看审计日志
- 主管可以查看审计日志
