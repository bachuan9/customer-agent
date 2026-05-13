# Complaint Priority Buttons Design

## Goal

Add frontend buttons in the complaint list to help users generate Agent commands for changing complaint priority.

## Scope

The buttons do not directly update the database. They only fill the chat input with a command the Agent already supports.

## Buttons

Each complaint row gets three new actions:

```text
高优先级 -> 设置投诉 C-0001 high
中优先级 -> 设置投诉 C-0001 medium
低优先级 -> 设置投诉 C-0001 low
```

## Data Flow

```text
Click priority button
-> web/app.js fillComplaintAction()
-> chat input is filled
-> user sends message
-> /chat
-> Agent
-> update_complaint priority
-> db.py
```

## Files

```text
web/app.js
```

