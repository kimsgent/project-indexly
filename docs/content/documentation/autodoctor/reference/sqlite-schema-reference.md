---
title: "SQLite Schema Reference"
linkTitle: "SQLite Schema"
description: "Authoritative SQLite schema reference for AutoDoctor tables, columns, indexes, and query patterns used by agent writers and API readers."
slug: "sqlite-schema-reference"
type: docs
aliases:
  - "/docs/autodoctor/reference/database/"
keywords:
  - "AutoDoctor SQLite schema"
  - "diagnostics table"
  - "telemetry_modules table"
tags:
  - "sqlite"
  - "reference"
  - "database"
categories:
  - "autodoctor"
weight: 53
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Use this schema map to validate writes, debug missing rows, and design safe query extensions."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Developers extending writes or API queries.
- Technical users validating data integrity after runs.

Schema source: `agent/core/db.schema.ps1`

## Table: `diagnostics`

Purpose: per-module run outcome and summary.

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` | PK, autoincrement |
| `run_id` | `TEXT` | Execution identifier |
| `hostname` | `TEXT` | Host name |
| `module_name` | `TEXT` | Module display name |
| `status` | `TEXT` | `Success` or `Failed` |
| `runtime_seconds` | `REAL` | Module runtime |
| `health_score` | `INTEGER` | Usually populated by root-cause row |
| `summary` | `TEXT` | Module summary text |
| `timestamp` | `DATETIME` | UTC insert timestamp |

Indexes:

- `idx_diag_timestamp` on `timestamp`
- `idx_diagnostics_run` on `run_id`

## Table: `remediation`

Purpose: remediation status record per run.

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` | PK, autoincrement |
| `run_id` | `TEXT` | Execution identifier |
| `hostname` | `TEXT` | Host name |
| `status` | `TEXT` | Remediation result status |
| `timestamp` | `DATETIME` | UTC insert timestamp |

## Table: `telemetry_modules`

Purpose: telemetry-level module status and key list.

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` | PK, autoincrement |
| `run_id` | `TEXT` | Execution identifier |
| `hostname` | `TEXT` | Host name |
| `module_name` | `TEXT` | Module display name |
| `status` | `TEXT` | Module success indicator |
| `result_keys` | `TEXT` | Comma-separated keys |
| `timestamp` | `DATETIME` | UTC insert timestamp |

Index:

- `idx_telemetry_modules_run_module` on `(run_id, module_name)`

## Table: `system_info`

Purpose: time-series metrics for dashboard charts.

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` | PK, autoincrement |
| `hostname` | `TEXT` | Host name |
| `cpu_load` | `REAL` | CPU load percent |
| `memory_free_gb` | `REAL` | Free memory in GB |
| `disk_free_gb` | `REAL` | Aggregated free disk space in GB |
| `network_latency_ms` | `REAL` | Measured latency |
| `timestamp` | `DATETIME` | UTC insert timestamp |

Indexes:

- `idx_system_info_timestamp` on `timestamp`
- `idx_system_info_host_time` on `(hostname, timestamp)`

## Table: `alerts`

Purpose: root-cause issue rows with severity.

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER` | PK, autoincrement |
| `run_id` | `TEXT` | Execution identifier |
| `hostname` | `TEXT` | Host name |
| `alert_type` | `TEXT` | Current value: `RootCause` |
| `severity` | `TEXT` | `Warning` or `Critical` |
| `message` | `TEXT` | Alert text |
| `timestamp` | `DATETIME` | UTC insert timestamp |

Indexes:

- `idx_alerts_timestamp` on `timestamp`
- `idx_alerts_severity` on `severity`

## High-Value Validation Queries

```sql
SELECT run_id, module_name, status, runtime_seconds
FROM diagnostics
ORDER BY id DESC
LIMIT 20;
```

```sql
SELECT severity, COUNT(*) AS count
FROM alerts
GROUP BY severity;
```

```sql
SELECT timestamp, cpu_load, memory_free_gb, disk_free_gb, network_latency_ms
FROM system_info
ORDER BY timestamp DESC
LIMIT 50;
```

## API Table Usage Map

- `/api/system/latest` and `/api/system/history` -> `system_info`
- `/api/alerts` -> `alerts`
- `/api/health` -> `diagnostics` (`health_score`)
- `/api/modules` -> `telemetry_modules`

## Next Steps

- [API Reference](./api-reference/)
- [Telemetry and Persistence](../developer-guide/telemetry-and-persistence/)
