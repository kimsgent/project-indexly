---
title: "Telemetry and Persistence"
linkTitle: "Telemetry + DB"
description: "How AutoDoctor builds telemetry, writes SQLite rows, stores metadata, and keeps API/dashboard reads consistent with current run context."
slug: "telemetry-and-persistence"
type: docs
aliases:
  - "/docs/autodoctor/developer-guide/persistence/"
keywords:
  - "AutoDoctor telemetry"
  - "SQLite write flow"
  - "latest_run.json"
tags:
  - "telemetry"
  - "sqlite"
  - "persistence"
categories:
  - "autodoctor"
weight: 43
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Trace data from module output to telemetry JSON, SQLite tables, and dashboard/API endpoints."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Developers troubleshooting missing dashboard data.
- Operators validating write/read consistency.

## Telemetry Collection Flow

1. `Invoke-AutoDoctorTelemetryCollection` builds telemetry object.
2. JSON file is written as UTF-8 without BOM.
3. `Write-AutoDoctorTelemetry` inserts module and system snapshot rows into SQLite.

Key telemetry object sections:

- `RunID`, `GeneratedAt`, `Hostname`, `AutoDoctorVersion`
- `ExecutionStats`
- `System`
- `Modules`

## DB Write Flow

### Diagnostics

`Write-AutoDoctorDiagnostics` inserts per-module status and summary into `diagnostics`.

### Remediation

`Write-AutoDoctorRemediation` inserts remediation module status into `remediation`.

### Telemetry

`Write-AutoDoctorTelemetry` writes:

- module-level status and keys into `telemetry_modules`
- derived system snapshot into `system_info`

### Alerts

`Write-AutoDoctorAlerts` maps root-cause detected issues into `alerts` with severity.

## Metadata File for Dashboard

`latest_run.json` is written at:

- `server/latest_run.json`

Fields:

- `run_id`
- `host_name`
- `generated_time`

The API endpoint `/api/dashboard/meta` reads this file and provides fallbacks if missing/corrupt.

## Concurrency Notes

API DB connections set:

- `PRAGMA journal_mode=WAL`
- `PRAGMA busy_timeout=5000`

This supports concurrent writer/reader behavior between agent and API.

## Validation Queries

```sql
SELECT COUNT(*) FROM diagnostics;
SELECT COUNT(*) FROM alerts;
SELECT COUNT(*) FROM telemetry_modules;
SELECT * FROM system_info ORDER BY timestamp DESC LIMIT 5;
```

## Next Steps

- Review [API Reference](../reference/api-reference/)
- Use [Troubleshooting Playbook](../troubleshooting/playbook/) when writes appear but dashboard is stale
