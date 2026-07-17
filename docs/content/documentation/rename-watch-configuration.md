---
title: "Evolve Rename Watch Configuration Safely"
linkTitle: "Rename Watch Configuration"
slug: "rename-watch-configuration"
aliases:
  - "/documentation/rename-watch-configuration/"
date: "2026-07-17"
lastmod: "2026-07-17"
weight: 32
type: docs
toc: true
draft: false
icon: "mdi:file-cog"
description: "Use the published Rename Watch JSON Schema, portable path expansion, and non-overwriting versioned migration workflow."
summary: "A compatibility-focused guide to Rename Watch schema validation, environment paths, configuration migration, restart rollout, and rollback."
keywords:
  - rename-watch JSON Schema
  - rename-watch configuration migration
  - Indexly environment variables
  - rename-watch version 1
tags:
  - rename-watch
  - configuration
  - JSON Schema
  - migration
categories:
  - Documentation
  - Automation
---

## Compatibility contract

Rename Watch currently supports configuration version `1`. Existing version-1
files remain valid without new keys, and omitted settings retain their
documented defaults. Unknown keys, a Boolean version such as `true`, and every
version other than the integer `1` fail closed.

Stage 6 adds validation and migration foundations; it does not introduce
configuration version 2 or live reload.

## Published JSON Schema

The Draft 2020-12 schema has a stable public URL:

```text
https://projectindexly.com/schemas/rename-watch-config-v1.schema.json
```

Use it in editor file associations or automation. For example, VS Code
`settings.json` can associate the schema without changing a configuration that
must remain readable by an older strict Indexly release:

```json
{
  "json.schemas": [{
    "fileMatch": ["**/rename-watch*.json"],
    "url": "https://projectindexly.com/schemas/rename-watch-config-v1.schema.json"
  }]
}
```

The same schema is packaged with Indexly under
`indexly.rename_watch/schemas/rename-watch-config-v1.schema.json`. The packaged
and website copies are tested byte-for-byte to prevent drift.

{{< alert title="Schema validation is the first check" color="info" >}}
JSON Schema validates document shape, required keys, types, enums, and numeric
bounds. `--check-config` remains authoritative for semantic and filesystem
rules such as unique job IDs, placeholder combinations, path containment,
cross-job subtree overlap, lock availability, durable state, and permissions.
{{< /alert >}}

## Path expansion

Expansion is intentionally limited to path fields that may point outside a
watch root.

| Input | Expansion | Relative base |
| --- | --- | --- |
| CLI `--config` | `${NAME}`, `$NAME`, and leading `~`; `%NAME%` is also accepted on Windows | Current working directory |
| Job `watch_path` | `${NAME}`, `$NAME`, and leading `~`; `%NAME%` is also accepted on Windows | Directory containing the configuration |
| `destination_subfolder` | None; it stays a literal relative child | `watch_path` |
| `quarantine_subfolder` | None; it stays a literal relative child | `watch_path` |
| IDs, patterns, globs, and other strings | None | Not applicable |

Use `${NAME}` for portable files. Expansion happens once when the configuration
is loaded. An undefined referenced variable fails validation instead of
creating a directory whose name still contains the expression. Leading `~`
means the current account's home only; `~other-user` is not a supported
portable shorthand.

Validate with the same environment and identity that will run the service:

```console
indexly rename-watch --config "${INDEXLY_CONFIG}/rename-watch.json" --check-config
```

Environment references are for paths, not secret storage. Do not put passwords,
tokens, service credentials, or private values in the JSON or path variables.
Resolved filesystem paths can appear in status output, diagnostics, and
rendered service templates.

## Canonical version-1 migration

Create a separate, deterministic configuration copy before any future format
upgrade:

```console
indexly rename-watch --config "./rename-watch.json" --migrate-config --output "./rename-watch.migrated.json"
```

For automation, add `--json`. Successful JSON output uses schema
`indexly.rename-watch.config-migration`, version `1`, and reports only source
version, target version, and output path. Configuration content is never
printed.

The migration command:

- accepts and validates only the exact integer version `1`;
- preserves environment and home expressions literally;
- preserves optional-key presence and never injects implicit defaults;
- sorts object keys and writes deterministic UTF-8 with one trailing newline;
- leaves array order and the source file unchanged;
- requires a distinct `.json` output in an existing real directory;
- atomically publishes a complete new file and refuses every overwrite;
- creates no watch, destination, quarantine, lock, runtime, log, or state path.

Running the command again from the first migrated file to another new output
produces identical bytes. Version 2 is intentionally refused until a reviewed
pure `1 -> 2` migration step and matching schema exist.

## Rollout and rollback

Use a stop-and-restart rollout because a running process captures configuration,
environment, selection rules, and service settings at startup:

1. Produce the new output and review its diff.
2. Run `--check-config` and `--once --dry-run` with the service identity.
3. Stop the manager and allow the configured drain deadline to complete.
4. Switch the manager to the reviewed configuration path.
5. Start it and verify `--health`, `--readiness`, and `--metrics`.
6. Keep the previous file unchanged for immediate rollback.

Rollback follows the same graceful stop, path switch, restart, and probe
sequence. A canonical version-1 copy has the same configuration semantics as
its source; key ordering is not semantic.

## Why live reload is deferred

There is no `--reload`, SIGHUP handler, or configuration file watcher. Safe live
reload would need one atomic design for watch-root lock changes, affected queue
draining, journal/counter/failure continuity, observer replacement and
rollback, plus concurrent status and readiness behavior. Until those invariants
are proven, restart is the supported configuration boundary.

Continue with [Rename Watch](/en/documentation/rename-watch/) for job behavior
and [Rename Watch Service Operation](/en/documentation/rename-watch-service-operation/)
for manager-specific rollout and rollback procedures.
