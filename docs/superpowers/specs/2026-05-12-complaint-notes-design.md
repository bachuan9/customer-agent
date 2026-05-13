# Complaint Notes Design

## Goal

Add customer-service notes for complaint work orders.

Each complaint can have many notes, so notes use a separate table instead of a single column on `complaints`.

## Commands

```text
备注投诉 C-0001 已联系用户，等待反馈
查看备注 C-0001
```

## Data Model

```text
complaints
  id

complaint_notes
  id
  complaint_id
  content
  author
  created_at
```

## Data Flow

```text
User message
-> /chat
-> agent.py detects add/list complaint notes
-> call_tool()
-> tools.py
-> db.py
-> complaint_notes table
```

## Frontend

The complaint table gets two buttons:

```text
添加备注 -> fills: 备注投诉 C-0001 
查看备注 -> fills: 查看备注 C-0001
```

Buttons still generate Agent commands instead of directly changing the database.

