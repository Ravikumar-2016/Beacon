# Finding Schema

## Final Report Structure

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": {
    "total_findings": 6,
    "critical": 1,
    "high": 2,
    "medium": 3
  },
  "findings": [
    {
      "id": "F-001",
      "title": "Short, descriptive title of the problem",
      "severity": "high",
      "evidence": "Specific, verifiable evidence describing what was detected and where.",
      "suggested_action": {
        "summary": "Actionable recommendation explaining what to change and what outcome it improves.",
        "priority": "high"
      }
    }
  ]
}
```

## Required Fields

### Report-level
| Field | Type | Description |
|---|---|---|
| `site` | string | Domain of the audited website |
| `audited_at` | ISO 8601 | Timestamp of audit completion |
| `summary` | object | Counts by severity level |
| `findings` | array | List of finding objects |

### Summary
| Field | Type | Description |
|---|---|---|
| `total_findings` | integer | Total number of findings |
| `critical` | integer | Count of critical findings |
| `high` | integer | Count of high findings |
| `medium` | integer | Count of medium findings |

### Finding
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Sequential ID: `F-001`, `F-002`, etc. |
| `title` | string | Yes | Clear, descriptive title |
| `severity` | string | Yes | One of: `critical`, `high`, `medium`, `low` |
| `evidence` | string | Yes | Specific, verifiable evidence |
| `suggested_action` | object | Yes | Recommended fix |

### Suggested Action
| Field | Type | Required | Description |
|---|---|---|---|
| `summary` | string | Yes | What to change and why |
| `priority` | string | Yes | One of: `critical`, `high`, `medium`, `low` |

## Internal Evidence Model

Specialist skills produce richer evidence before the orchestrator converts to final findings:

```json
{
  "url": "https://example.com/product/test",
  "crawl": {
    "status": 200,
    "redirects": [],
    "robots_allowed": true
  },
  "render": {
    "raw_text_length": 183,
    "rendered_text_length": 1240,
    "content_difference_ratio": 0.85
  },
  "structured_data": {
    "jsonld_count": 1,
    "types": ["Product"],
    "valid_json": true
  },
  "metadata": {
    "title": "Example Product",
    "description_present": true
  },
  "headings": {
    "h1": ["Example Product"],
    "h2": ["Specifications", "Pricing"]
  }
}
```

This model may be extended by specialist skills as needed.

## Finding ID Assignment

- IDs are assigned sequentially across all skills after deduplication.
- The orchestrator controls ID assignment, not individual skills.
- Internal skill evidence uses detector category IDs (C1–C12, F1–F6, E1–E13) before final assignment.
