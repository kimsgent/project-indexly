---
title: "Operate Rename Watch as a Service"
linkTitle: "Rename Watch Service"
slug: "rename-watch-service-operation"
aliases:
  - "/documentation/rename-watch-service-operation/"
date: "2026-07-17"
lastmod: "2026-07-17"
weight: 32
type: docs
toc: true
draft: false
icon: "mdi:cog-sync"
description: "Install, monitor, upgrade, roll back, and remove Indexly Rename Watch services safely on Windows, Linux, and macOS."
summary: "Production-oriented WinSW, systemd, and launchd procedures for Rename Watch, including graceful draining, health probes, metrics, permissions, logs, and rollback."
keywords:
  - indexly rename-watch service
  - rename-watch systemd
  - rename-watch launchd
  - rename-watch Windows service
  - WinSW indexly
  - file watcher monitoring
tags:
  - rename-watch
  - service operation
  - systemd
  - launchd
  - WinSW
categories:
  - Documentation
  - Operations
  - Automation
---

## Overview

Rename Watch can run continuously under Windows Service Control Manager,
systemd, or macOS launchd. Indexly supplies portable service templates while
leaving account creation, directory permissions, and service-manager changes
under administrator control.

This guide assumes that the normal Rename Watch workflow already succeeds. If
you have not validated and previewed the configuration, start with
[Rename Watch](/en/documentation/rename-watch/).

{{< alert title="Use hybrid mode for unattended operation" color="warning" >}}
The supplied templates supervise one continuously running process. Configure
jobs in `hybrid` mode unless you deliberately accept event-only limitations.
Hybrid reconciliation rediscovers unchanged files after a restart; event mode
does not perform that reconciliation.
{{< /alert >}}

## Service settings

The optional top-level `service` object controls the process lifecycle and its
private live-status snapshot. Existing version-1 configurations that omit it
retain the defaults.

```json
{
  "version": 1,
  "service": {
    "shutdown_drain_timeout_seconds": 30,
    "health_interval_seconds": 5,
    "health_stale_after_seconds": 15
  },
  "jobs": [{
    "id": "inbox",
    "watch_path": "./inbox",
    "destination_subfolder": "processed",
    "mode": "hybrid"
  }]
}
```

| Setting | Purpose | Default |
| --- | --- | --- |
| `shutdown_drain_timeout_seconds` | One process-wide deadline for stopping intake and draining pending candidates. | `30` |
| `health_interval_seconds` | Interval between atomic live-status heartbeat updates. | `5` |
| `health_stale_after_seconds` | Age after which a heartbeat is unhealthy; it must be greater than the heartbeat interval. | `15` |

All three values must be finite positive numbers. The service-manager stop
timeout must be longer than `shutdown_drain_timeout_seconds`; allow at least
another 5–10 seconds for observer cleanup and final state publication.

## Understand graceful shutdown

The first supported stop request, including `SIGTERM` from systemd or launchd,
starts a bounded drain:

1. Readiness changes to false and new filesystem events are no longer accepted.
2. Filesystem observers and periodic reconciliation stop.
3. Already pending settling and retry work runs without adding a reconciliation
   scan, until the queue empties or the configured deadline expires.
4. Active durable move, failure, and audit boundaries finish before locks are
   released.
5. The final runtime snapshot records any abandoned pending count, then the
   process exits.

A second stop request shortens the remaining drain to an immediate deadline.
Drain timeout does not turn an untouched source into a terminal failure and
does not emit a false `RENAME_WATCH_FAILED` audit event. Hybrid and interval
jobs rediscover an abandoned source during later reconciliation.

Event-only jobs need special care: an unchanged pending source abandoned at
shutdown may generate no new filesystem event after restart. If the metrics
report abandoned pending work, stop the service and process a controlled
`--once` run, touch or replace the affected inputs so they emit new events, or
temporarily use `hybrid` mode. Use hybrid mode when restart recovery of
process-local pending work is required.

The timeout is cooperative. It bounds settling, retry, and observer cleanup,
but the service manager may still have to terminate a process stuck inside an
uninterruptible operating-system filesystem call.

## Health, readiness, metrics, and durable status

Run probes with the same absolute configuration path and `INDEXLY_HOME` used
by the service:

```console
indexly rename-watch --config "/path/to/rename-watch.json" --health
indexly rename-watch --config "/path/to/rename-watch.json" --readiness
indexly rename-watch --config "/path/to/rename-watch.json" --metrics
```

Add `--json` for automation:

```console
indexly rename-watch --config "/path/to/rename-watch.json" --readiness --json
```

| Probe | Question answered | JSON schema |
| --- | --- | --- |
| `--health` | Is a valid service heartbeat present and fresh? | `indexly.rename-watch.health`, version 1 |
| `--readiness` | Has startup completed, and is the process accepting work rather than draining? | `indexly.rename-watch.readiness`, version 1 |
| `--metrics` | What has this process scheduled, processed, moved, retried, failed, recovered, left pending, or abandoned? | `indexly.rename-watch.metrics`, version 1 |

A successful probe exits `0`. An unavailable, stale, unhealthy, or not-ready
live service exits `4`; distinguish that result from usage (`2`) and
configuration or safety refusal (`3`). Probe data comes from a bounded,
schema-validated, atomic file under
`INDEXLY_HOME/rename-watch/runtime/<service-namespace>.json`. It is private
runtime state, not an API to edit.

Metrics are scoped to the current process lifetime. The version-1 fields are
`scans`, `scheduled`, `processed`, `moved`, `retries`,
`terminal_failures`, `audit_write_failures`, `recovered_moves`, `pending`, and
`shutdown_abandoned_pending`. They do not use raw source or destination paths
as labels and are not written as generic Indexly index events.

`--status` remains the durable operational view. It reports configured jobs,
recovery journals, active durable failures, and retained audit history, but it
does not pretend that a live process-local queue is available. Use readiness
for traffic decisions, health for heartbeat monitoring, metrics for the current
process, and status for durable investigation.

## Prepare a service deployment

Complete these steps on every platform before installing a manager template:

1. Install Indexly in a dedicated, versioned virtual environment. Record the
   absolute Python executable; templates do not depend on an interactive
   `PATH`.
2. Put the configuration in an administrator-managed location. The service
   account needs read access but should not own or modify it.
3. Create a dedicated `INDEXLY_HOME`. File-based manager output is kept below
   its derived `service-logs` directory, separate from audit NDJSON under `log`.
4. Grant the service identity only the permissions listed below.
5. Set `INDEXLY_HOME`, then validate and preview as the service identity:

   ```console
   python -m indexly rename-watch --config "/absolute/rename-watch.json" --check-config
   python -m indexly rename-watch --config "/absolute/rename-watch.json" --once --dry-run
   ```

6. Render the packaged template from that same environment. The renderer fills
   the absolute Python executable, configuration, runtime root, derived manager
   log directory, account, and manager timeout. It refuses to overwrite an existing
   output.

   ```console
   python -m indexly rename-watch --config "/absolute/rename-watch.json" \
     --export-service-template systemd --output "./indexly-rename-watch.service" \
     --service-user indexly --service-group indexly
   ```

Available template IDs are `windows`, `systemd`, `launchd`, and
`launchd-newsyslog`. Every export requires `--output`. Windows also requires
`--service-user`; the other three require both `--service-user` and
`--service-group`. The Windows renderer accepts only
`NT AUTHORITY\LocalService` or a `DOMAIN\account$` gMSA and rejects percent
characters in rendered values because WinSW treats percent-delimited text as
environment expansion syntax.

{{< alert title="Review before installing" color="info" >}}
Template export writes a portable starting point; it does not create accounts,
change ACLs, install WinSW, call `systemctl` or `launchctl`, or elevate itself.
Review the rendered paths, account, timeout, restart policy, and log destination
before installing it.
{{< /alert >}}

## Least-privilege permissions

The service identity needs:

- read and execute access to its versioned Python environment;
- read access to the Rename Watch JSON configuration and any root-local
  `.indexlyignore` files it uses;
- traverse, read, create, rename, and delete access within configured watch,
  destination, and quarantine trees;
- read and write access to `INDEXLY_HOME`, including runtime state, logs,
  counters, journals, backups, and durable failures;
- write access to the separate manager stdout/stderr directory when the manager
  does not use its own journal.

Do not run as Windows LocalSystem or POSIX root. Do not put credentials in the
JSON or rendered template. Keep the configuration administrator-owned and
limit who can write parent directories; changing a protected path component
to a symlink or Windows reparse point causes Rename Watch to fail closed.

For network storage, grant the account explicit remote permissions. Windows
services should use UNC paths rather than interactive drive mappings. On macOS,
privacy protections can deny a launch daemon access to Desktop, Documents,
Downloads, removable volumes, or network volumes even when POSIX permissions
look correct. Validate access as the actual launchd identity.

## Windows service with WinSW

Indexly is a console application, so Windows Service Control Manager cannot
run it directly as a conforming service. The supported template uses the
external [Windows Service Wrapper (WinSW)](https://github.com/winsw/winsw).
Indexly does not download or bundle WinSW.

1. Create versioned application and data locations, for example:

   ```text
   C:\Program Files\Indexly\venvs\2.1.5\
   C:\ProgramData\Indexly\rename-watch.json
   C:\ProgramData\Indexly\state\
   C:\ProgramData\Indexly\state\service-logs\
   C:\ProgramData\Indexly\service\
   ```

2. Use `NT AUTHORITY\LocalService` for local paths, or a group Managed Service
   Account (gMSA) when managed network identity is required. Grant it the
   required ACLs and service-logon rights. The rendered XML never contains a
   password; an ordinary dedicated user is therefore not supported by this
   password-free template.
3. Download a pinned WinSW release from its official release page and verify
   its published checksum according to your software-supply policy.
4. Set the service's runtime root and export the Windows template from the
   versioned Indexly environment:

   ```powershell
   $env:INDEXLY_HOME = 'C:\ProgramData\Indexly\state'
   & 'C:\Program Files\Indexly\venvs\2.1.5\Scripts\python.exe' -m indexly `
     rename-watch --config 'C:\ProgramData\Indexly\rename-watch.json' `
     --export-service-template windows --output '.\indexly-rename-watch.xml' `
     --service-user 'NT AUTHORITY\LocalService'
   ```
5. Place the verified WinSW executable beside the XML and rename it
   `indexly-rename-watch.exe`.
6. In an elevated PowerShell terminal, install and start it:

   ```powershell
   .\indexly-rename-watch.exe install
   .\indexly-rename-watch.exe start
   .\indexly-rename-watch.exe status
   ```

7. Run `--health`, then `--readiness`, using the service's `INDEXLY_HOME`.

WinSW sends Ctrl+C to the console child and waits for the rendered
`<stoptimeout>` before forced termination. The template uses delayed automatic
start, restart-on-failure, and bounded size-based wrapper logs. These wrapper
logs are separate from Rename Watch audit NDJSON. Do not add WinSW
`<hidewindow>true</hidewindow>`: its `CreateNoWindow` behavior can prevent the
Ctrl+C path on which graceful draining depends. Windows services are already
noninteractive.

## Linux service with systemd

The following example uses `indexly` as a dedicated system user and group,
`/etc/indexly/rename-watch.json` as administrator-managed configuration, and
`/var/lib/indexly-rename-watch` as `INDEXLY_HOME`.

1. Create the account, directories, versioned virtual environment, and
   permissions using your distribution's account-management tools.
2. Export and review `indexly-rename-watch.service` from the versioned
   environment.
3. Install and verify the unit:

   ```bash
   sudo install -o root -g root -m 0644 indexly-rename-watch.service \
     /etc/systemd/system/indexly-rename-watch.service
   sudo systemd-analyze verify /etc/systemd/system/indexly-rename-watch.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now indexly-rename-watch.service
   sudo systemctl status indexly-rename-watch.service
   ```

4. Run the readiness probe with the unit's `INDEXLY_HOME` and inspect logs:

   ```bash
   sudo -u indexly env INDEXLY_HOME=/var/lib/indexly-rename-watch \
     /opt/indexly/venvs/2.1.5/bin/python -m indexly rename-watch \
     --config /etc/indexly/rename-watch.json --readiness
   sudo journalctl -u indexly-rename-watch.service
   ```

The unit uses `Type=simple`, sends `SIGTERM`, applies one `TimeoutStopSec`,
restarts only after failure, and enables `NoNewPrivileges`. It deliberately
does not enable `PrivateTmp`: Rename Watch uses a fixed shared `/tmp` lock
namespace to exclude another process consuming the same canonical watch root.
Do not add `PrivateTmp=true` in a drop-in.

Generic templates also avoid `ProtectHome` and strict write-path allowlists
because valid watch roots can be under home directories or mounted elsewhere.
After choosing fixed production paths, administrators may add a reviewed
systemd hardening drop-in that still permits every watch tree and
`INDEXLY_HOME`.

## macOS service with launchd

The supplied plist is a system launch daemon. A portable system deployment can
keep administrator-managed configuration, a versioned environment, and
runtime state below `/Library/Indexly`, with `INDEXLY_HOME` set to
`/Library/Indexly/state`. This no-space path also allows the derived
`service-logs` directory to be represented safely in newsyslog fields.

1. Provision a dedicated non-login account and group using an approved macOS
   management method. Grant only the permissions described above.
2. Export `launchd` and `launchd-newsyslog` templates from the versioned
   environment. Use a service-log path without spaces because newsyslog fields
   are whitespace-delimited.

   ```bash
   export INDEXLY_HOME=/Library/Indexly/state
   /Library/Indexly/venvs/2.1.5/bin/python -m indexly rename-watch \
     --config /Library/Indexly/rename-watch.json \
     --export-service-template launchd \
     --output ./com.projectindexly.rename-watch.plist \
     --service-user _indexly --service-group _indexly
   /Library/Indexly/venvs/2.1.5/bin/python -m indexly rename-watch \
     --config /Library/Indexly/rename-watch.json \
     --export-service-template launchd-newsyslog \
     --output ./indexly-rename-watch.newsyslog.conf \
     --service-user _indexly --service-group _indexly
   ```
3. Validate and install the files:

   ```bash
   plutil -lint com.projectindexly.rename-watch.plist
   sudo install -o root -g wheel -m 0644 \
     com.projectindexly.rename-watch.plist \
     /Library/LaunchDaemons/com.projectindexly.rename-watch.plist
   sudo install -o root -g wheel -m 0644 \
     indexly-rename-watch.newsyslog.conf \
     /etc/newsyslog.d/indexly-rename-watch.conf
   sudo launchctl bootstrap system \
     /Library/LaunchDaemons/com.projectindexly.rename-watch.plist
   sudo launchctl enable system/com.projectindexly.rename-watch
   sudo launchctl kickstart -k system/com.projectindexly.rename-watch
   sudo launchctl print system/com.projectindexly.rename-watch
   ```

4. Run readiness under the same account and `INDEXLY_HOME`.

The plist uses absolute tokenized `ProgramArguments`, a dedicated user and
group, `KeepAlive` only after unsuccessful exit, bounded restart throttling,
and `ExitTimeOut` longer than the application drain. Its stdout and stderr files
are rotated independently by the supplied newsyslog rule.

## The three log and state classes

Do not treat all service files as one retention domain:

| Class | Location and retention | Purpose |
| --- | --- | --- |
| Rename Watch audit NDJSON | `INDEXLY_HOME/log/YYYY/MM/`; daily partitions, 5 MiB rollover, 30-day retention applied when a later event is written | Successful moves and terminal failures; retained history is not a lifetime total. |
| Durable operational state | `INDEXLY_HOME/rename-watch/`; no log-rotation deletion | Recovery journals, counters, counter backups, durable failures, and the private runtime snapshot. |
| Manager stdout/stderr | WinSW rolling files, systemd journal, or launchd files with newsyslog | Startup, wrapper, and process diagnostics outside the audit-event schema. |

Log rotation never resolves or deletes an actionable durable failure. Audit
delivery remains at least once across interruption; use `operation_id` to
deduplicate successful moves. Because NDJSON retention is applied during a
subsequent write, an idle installation can retain an already expired file until
the next audit event.

For Windows startup failures, inspect the WinSW wrapper log, its rolled child
output, and Windows Event Log. For systemd use `journalctl -u`. For launchd use
`launchctl print`, the configured stdout/stderr files, and the macOS unified
log.

## Upgrade safely

1. Record the running Indexly and template versions. Back up the JSON
   configuration and installed service definition.
2. Preserve the complete `INDEXLY_HOME`. Do not edit or discard pending
   journals, counter state, or durable failure records.
3. Install the new Indexly version beside the current environment.
4. Stop the service and wait for its manager to report stopped. Check
   `shutdown_abandoned_pending` and investigate event-only jobs before
   continuing.
5. As the service identity, run the new executable with `--check-config` and
   `--once --dry-run` against the production configuration.
6. Export a new manager template, review its diff, and install or refresh it.
7. Start the service. Require both health and readiness to succeed, then review
   metrics, durable status, audit logs, and manager logs.
8. Keep the previous environment and configuration copy until the observation
   window passes.

Do not run `pip install --upgrade` inside the active environment while the
service is running. A side-by-side environment makes the executable change
atomic from the manager's perspective and preserves a tested rollback target.

## Roll back safely

1. Stop and drain the current service.
2. Restore the previous executable reference, compatible JSON configuration,
   and manager template.
3. Keep the current durable state. Never restore older journals, counters, or
   failure records over newer state: the filesystem may already reflect moves
   committed after that backup.
4. Run the previous version's `--check-config` as the service identity.
5. Start it and verify health, readiness, status, audit logs, and manager logs.

Older Indexly releases reject unknown configuration keys. Retain a known-good
configuration for each rollback target; for a pre-Stage-5 version, that may
mean a copy without the optional top-level `service` object.

## Remove a service

Stop and unregister the manager before removing executable files.

Windows with installed, colocated WinSW:

```powershell
.\indexly-rename-watch.exe stop
.\indexly-rename-watch.exe uninstall
```

systemd:

```bash
sudo systemctl disable --now indexly-rename-watch.service
sudo rm /etc/systemd/system/indexly-rename-watch.service
sudo systemctl daemon-reload
```

launchd:

```bash
sudo launchctl bootout system/com.projectindexly.rename-watch
sudo rm /Library/LaunchDaemons/com.projectindexly.rename-watch.plist
sudo rm /etc/newsyslog.d/indexly-rename-watch.conf
```

Removing a service definition does not authorize deleting its configuration,
watch folders, processed files, quarantine, or `INDEXLY_HOME`. Retain those
until recovery journals, failures, audit requirements, and rollback needs have
been reviewed.

## Lock and account changes

Run `--check-config` as the final service identity before first start and after
changing accounts. Windows uses a global named mutex. Linux and macOS use a
fixed `/tmp/indexly-rename-watch-<hash>.lock` file with operating-system locking;
the file can remain after a clean shutdown and is not by itself evidence of a
running process.

The POSIX lock file is created with mode `0600`. A file left by a previous
service identity can prevent a replacement identity from opening it. Confirm
that no Rename Watch process owns the affected canonical root before removing
only the exact stale lock file, then rerun `--check-config` as the new identity.
Never delete broad `/tmp` paths or lock files while ownership is uncertain.

## Operational checklist

Before declaring a deployment healthy:

- `--check-config` succeeds as the service identity;
- a reviewed `--once --dry-run` matches the intended roots and destinations;
- the manager timeout exceeds the application drain timeout;
- health and readiness both exit `0` with the manager environment;
- metrics show no unexplained audit failures or abandoned pending work;
- durable `--status` has no unexpected recovery conflict or active failure;
- audit and manager log retention are both configured and tested;
- the previous environment and compatible configuration remain available for
  rollback.

## See also

- [Rename Watch](/en/documentation/rename-watch/) for configuration, selection, counters, failures, and recovery.
- [Indexly Logging System](/en/documentation/indexly-logging-system/) for the shared NDJSON log format.
- [Install Indexly](/en/documentation/indexly-installation/) for product installation and optional feature packs.
