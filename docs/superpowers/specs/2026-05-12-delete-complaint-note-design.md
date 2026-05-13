# Delete Complaint Note Design

## Goal

Add support for deleting one complaint note by note id.

Supported Agent command:

```text
删除备注 N-0001
```

## Scope

Deleting a note only removes one row from `complaint_notes`.

It does not delete the parent complaint.

## Data Flow

```text
User message
-> /chat
-> agent.py detects delete_complaint_note
-> call_tool("delete_complaint_note", {"note_id": "N-0001"})
-> tools.py
-> db.py
-> DELETE FROM complaint_notes WHERE id = ?
```

## API

```text
DELETE /complaint-notes/{note_id}
```

## Frontend

The first version supports manual Agent input. The user can copy note ids from `查看备注 C-0001` output and send:

```text
删除备注 N-0001
```

