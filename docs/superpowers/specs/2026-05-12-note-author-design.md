# Complaint Note Author Design

## Goal

Let complaint notes store a real customer-service author instead of always using the default `客服`.

## Command Format

```text
备注投诉 C-0001 Alice: 已联系用户
```

If no author is provided:

```text
备注投诉 C-0001 已联系用户
```

the author stays:

```text
客服
```

## Frontend

Add an `agentName` input. The "添加备注" button generates:

```text
备注投诉 C-0001 Alice: 
```

using the current agent name.

## Backend

Agent extracts:

```text
author = Alice
content = 已联系用户
```

Then calls:

```text
call_tool("add_complaint_note", {"complaint_id": "C-0001", "content": "...", "author": "Alice"})
```

