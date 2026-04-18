---
title: "Architecture Overview"
linkTitle: "Architecture"
description: "Technical architecture of AutoDoctor across agent, persistence, reporting, API service, and dashboard layers, including runtime boundaries and data flow."
slug: "architecture-overview"
aliases:
  - "/docs/autodoctor/developer-guide/architecture/"
keywords:
  - "AutoDoctor architecture"
  - "PowerShell FastAPI SQLite"
  - "agent server data flow"
tags:
  - "architecture"
  - "developer-guide"
  - "design"
categories:
  - "autodoctor"
weight: 41
date: "2026-03-15"
lastmod: "2026-04-17"
draft: false
params:
  summary: "Understand subsystem boundaries and end-to-end execution flow before extending AutoDoctor."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Developers extending diagnostics/remediation modules.
- Operators debugging interactions between agent and API.

## High-Level Components

- `agent/`: PowerShell orchestration, modules, telemetry, SQLite writes
- `agent/core/report.ps1`: HTML, JSON, Markdown, and optional PDF report generation
- `server/api/`: FastAPI app, SQLite query layer, service wrapper
- `server/dashboard/`: static dashboard + Chart.js polling client
- `config/`: INI template and runtime config
- `installer/`: build and Inno packaging scripts

## Execution Flow

1. Agent entrypoint (`AutoDoctor.ps1`) initializes paths and DB.
2. Module engine executes collection modules, then validation/history/anomaly/correlation.
3. Root cause and remediation run, then results are persisted.
4. HTML, JSON, Markdown, and optional PDF reports are generated.
5. Telemetry JSON and `latest_run.json` are written.
6. API reads SQLite + metadata + report JSON and serves endpoints.
7. Dashboard polls API every 5 seconds.

```text
AutoDoctor.ps1
  -> module engine
  -> rootcause + remediation
  -> SQLite writes + telemetry snapshots
  -> report generation (HTML / JSON / MD / PDF)
  -> latest_run.json
  -> FastAPI endpoints
  -> dashboard UI
```

## Service Runtime Flow

- Service wrapper (`autodoctor_service.py`) resolves runtime paths and mode.
- Child API process starts from bundled binary or source script depending on mode.
- API binds host/port based on precedence (registry -> INI -> env -> defaults).

## Key Design Characteristics

- Local-first storage and runtime
- SQLite as shared state between writer (agent) and reader (API)
- Report JSON as a second read model for higher-level dashboard summaries
- Configurable service registration mode for constrained environments
- Clear separation of collection (agent) and presentation (API/dashboard)

## Next Steps

- Read [Module Engine and Data Contracts](./module-engine-contracts/)
- Read [Telemetry and Persistence](./telemetry-and-persistence/)
