# Complaint Detail Design

## Goal

Add a detail view for one complaint.

Supported Agent command:

```text
查看投诉 C-0001
```

## Response Content

The detail includes:

```text
complaint fields
notes list
```

## API

```text
GET /complaints/{complaint_id}
```

Returns:

```text
{
  "complaint": {...},
  "notes": [...]
}
```

## Frontend

Add one row action:

```text
查看详情 -> 查看投诉 C-0001
```

The button still fills an Agent command instead of directly loading details.

