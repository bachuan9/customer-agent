# Complaint Filter Design

## Goal

Add complaint list filtering by:

```text
user_id
status
priority
handler
```

## API

```text
GET /complaints?status=processing&priority=high&handler=Alice&user_id=user1
```

All parameters are optional.

## Agent Commands

Support common commands:

```text
查看高优先级投诉
查看处理中投诉
查看待处理投诉
查看已解决投诉
查看 Alice 的投诉
```

## Frontend

Add quick filter buttons:

```text
高优先级投诉
处理中投诉
待处理投诉
已解决投诉
```

Buttons still generate Agent commands instead of directly querying the database.

## Data Flow

```text
Agent command
-> agent.py extracts filters
-> call_tool("list_complaints", filters)
-> tools.py
-> db.py fetch_complaints(...)
-> SELECT ... WHERE ...
```

