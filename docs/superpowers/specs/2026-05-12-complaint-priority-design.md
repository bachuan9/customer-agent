# Complaint Priority Update Design

## Goal

Add a small backend learning feature: allow the Agent flow to update a complaint work order's `priority`.

Supported command:

```text
设置投诉 C-0001 high
```

Supported priority values:

```text
low
medium
high
```

## Scope

This change only supports manual Agent commands first. It does not add new frontend buttons yet.

## Data Flow

```text
User message
-> /chat
-> agent.py detects update_complaint_priority
-> handle_intent extracts complaint_id and priority
-> call_tool("update_complaint", ...)
-> tools.py forwards priority
-> db.py validates and writes priority
-> Agent returns updated complaint summary
```

## Files

```text
app/storage/db.py
app/services/tools.py
app/services/tool_registry.py
app/services/agent.py
app/models/schemas.py
```

## Rules

`priority` must be one of:

```text
low
medium
high
```

Invalid priorities return an error instead of writing bad data.

