---
title: "Backup & Restore"
description: "Incremental, encrypted backups with automatic scheduling and reliable restore chains in Indexly."
slug: "backup-restore"
weight: 160
lastmod: "2026-05-13"
type: docs
draft: false
keywords: [
    "indexly backup",
    "incremental backup",
    "encrypted backup",
    "restore",
    "checksum",
    "automation"
]
---

## Overview

Indexly provides a **robust, incremental backup and restore system** designed for reliability, transparency, and automation. It supports:

- Full and incremental backups
- Encrypted archives (`.enc`)
- Strong checksum verification
- Automatic scheduled backups
- Safe restore with chain reconstruction

Backups are optimized for long-term storage and predictable restores.

----

## Backup Types

### Full Backup

A full backup captures the **entire folder state** at a point in time.

```bash
indexly backup "E:\data"
```

- Required as the base for incrementals
- Self-contained
- Recommended periodically

----

### Incremental Backup

Incremental backups store **only changes since the last backup**.

```bash
indexly backup "E:\data" --incremental
```

- Faster
- Smaller archives
- Requires restore chain

Indexly automatically determines the correct base.

![scaled_backup_03.jpeg](/images/scaled_backup_03.png)

----

## Encryption

### Encrypted Backups

Backups can be encrypted using a password:

```bash
indexly backup "E:\data" --encrypt "Better-Password-2026"
```

- Encryption happens **after compression**
- Resulting file ends with `.enc`
- Registry tracks encryption state
- Passwords must be at least 12 characters and include upper/lowercase letters, a digit, and a symbol

Example:

```shell
full_2026-01-01_191528.tar.zst.enc
```

The original archive is replaced by its encrypted form (`.enc`).

----

## Checksums

Indexly generates a SHA-256 checksum for every backup:

```shell
full_2026-01-01_191528.tar.zst.enc.sha256
```

- Always computed on the final stored archive, including `.enc` files
- Ensures archive integrity
- Verified automatically during restore

Older backups that used the previous checksum filename format remain restorable.

----

## Backup Verification

Verify all registered backups without restoring them:

```bash
indexly backup --verify
```

Verify a single archive by filename:

```bash
indexly backup --verify full_2026-01-01_191528.tar.zst.enc --decrypt "Better-Password-2026"
```

Verification checks:

- Archive checksum
- Decryption, when `.enc` is detected
- Safe extraction into a temporary directory
- Manifest and metadata readability
- Payload checksums for files stored inside the archive

No files are written to your restore target during verification.

----

## Compression

Indexly automatically selects the best available compression:

| **Method** | **Extension** | **Condition**    |
| ---------- | ------------- | ---------------- |
| Zstandard  | `.tar.zst`    | `zstd` available |
| Gzip       | `.tar.gz`     | fallback         |

Detection is runtime-based. If `zstd` is not available, Indexly falls back to gzip when creating new backups.

When restoring existing `.tar.zst` archives, Indexly can use either the Python `zstandard` package or the `zstd` CLI.

Install `zstd` by platform:

- Windows (PowerShell): `winget install Facebook.Zstandard`
- macOS: `brew install zstd`
- Debian/Ubuntu: `sudo apt-get install zstd`

----

## Restore Process

### Basic Restore

```bash
indexly restore full_2026-01-01_191528.tar.zst.enc --target "E:\restore"
```

### Encrypted Restore

- Encryption is auto-detected via `.enc`
- No extra flags required
- Password prompt allows **3 attempts**

```shell
🔐 Enter password (attempt 1/3)
```

If decryption fails after 3 attempts, restore aborts safely.

### Restore Dry-Run

Use dry-run mode to verify and simulate a restore chain without writing files to the destination:

```bash
indexly restore incremental_2026-01-02_080000.tar.gz --target "E:\restore" --dry-run
```

Dry-run mode verifies checksums, decrypts when needed, extracts into temporary storage, replays the final snapshot, and reports the resulting file count. The target folder is left untouched.

----

## Incremental Restore Chains

Restoring an incremental backup automatically:

1. Locates the base full backup
2. Replays all incrementals in order
3. Verifies checksums at each step
4. Applies deletion-only incrementals from the manifest snapshot

> Incremental restore chains are reconstructed automatically during restore, so users only need to restore the latest archive—Indexly handles the rest.

----

## Automatic Backups

Automatic backups in Indexly are designed to be **explicit, transparent, and user-controlled**.
Instead of silently running in the background, Indexly **creates a runnable backup script** that you can review, schedule, and manage yourself.

This approach gives you:

- Full visibility into what runs
- OS-native scheduling (no hidden daemons)
- Enterprise-grade structured logs
- Easy enable/disable behavior

----

### Step 1: Initialize Automatic Backup

To enable automatic backups for a folder, run:

```bash
indexly backup "E:\data" --init-auto
```

What happens next, step by step:

1. Indexly creates the backup directory structure in:

```shell
~/Documents/indexly-backups/
```

1. An **auto-backup marker** (`auto_enabled.json`) is written.
2. A **platform-specific backup script** is generated:
    - Windows → `indexly_backup.bat`
    - macOS / Linux → `indexly_backup.sh`
1. The script is pre-filled with:
    - Your backup source path
    - Log directory
    - Safe defaults for Python and Indexly execution

You’ll see confirmation in the terminal along with the script location.

Indexly validates that the source exists, is readable, and is not inside the backup storage directory before a backup runs. It also checks available disk space before writing archives.

----

### Step 2: Understand the Generated Script

Indexly intentionally generates a **plain, readable script** so you always know what runs.

#### Example: Windows `indexly_backup.bat`

```bash
+--------------------------------------------------+
| indexly_backup.bat                               |
+--------------------------------------------------+
| @echo off                                        |
|                                                  |
| set INDEXLY_EXE=indexly                          |
| set BACKUP_SOURCE=E:\data                        |
| set LOG_DIR=C:\Users\User\Documents\             |
|   indexly-backups\logs                           |
|                                                  |
| set TIMESTAMP=2026-01-04_020000                  |
| set LOG_FILE=%LOG_DIR%\backup_%TIMESTAMP%.log    |
|                                                  |
| "%INDEXLY_EXE%" backup "%BACKUP_SOURCE%"         |
|   >> "%LOG_FILE%" 2>&1                           |
+--------------------------------------------------+
```

Key points:

- **No hardcoded project paths**
- Works for both developers and non-developers
- Uses virtual environment Python if available
- Falls back to system Python and PATH-installed `indexly`
- Falls back to `python -m indexly` if the `indexly` command is not discoverable

You are encouraged to open and inspect this file.

----

### Step 3: Schedule the Script (User-Controlled)

Indexly does **not** auto-schedule tasks for you.
This is intentional — you stay in control.

#### Windows (Task Scheduler)

- Schedule `indexly_backup.bat`
- Run daily, weekly, or on login
- Use highest privileges if backing up protected folders

#### macOS / Linux (cron)

```bash
0 2 * * * /path/to/indexly_backup.sh
```

Runs daily at 02:00.

For detailed scheduler instructions, see:

- Microsoft Task Scheduler docs:
[https://learn.microsoft.com/windows/win32/taskschd/task-scheduler-start-page](https://learn.microsoft.com/windows/win32/taskschd/task-scheduler-start-page)
- Cron reference:
[https://man7.org/linux/man-pages/man5/crontab.5.html](https://man7.org/linux/man-pages/man5/crontab.5.html)

----

## Logging & Observability (New)

Automatic backups use **enterprise-grade structured JSON logs**.

### Where Logs Are Stored

All auto-backup logs are written to:

```shell
~/Documents/indexly-backups/logs/
```

Each run produces a timestamped `.log` file.

### Log Format

- One JSON object per line
- UTC timestamps
- Event-driven structure
- Safe for automation and auditing

Example entry:

```json
{
  "schema": "indexly.log",
  "version": 1,
  "ts": "2026-01-04T01:59:12.341Z",
  "level": "INFO",
  "component": "auto-backup",
  "event": "backup.complete",
  "message": "Incremental backup completed successfully",
  "context": {
    "source": "E:\\data"
  }
}
```

----

### Viewing Logs in the Terminal

#### macOS / Linux

```bash
cat backup_2026-01-04_020000.log | jq
```

#### Windows (PowerShell)

```shell
type backup_2026-01-04_020000.log | jq
```

To install `jq` on Windows:

```shell
scoop install jq
```

If your Windows shell environment is not ready yet, use the maintained [Windows Development Environment Setup](windows-terminal-setup.md) guide instead of the old Windows Terminal customization flow.

----

## Disabling Automatic Backups

To safely disable auto-backups:

```bash
indexly backup "E:\data" --disable-auto --confirm
```

This will:

1. Remove the auto-backup marker
2. Delete the generated `.bat` / `.sh` script
3. Prevent any further scheduled runs

Nothing is left behind unintentionally.

----

## Summary

Automatic backups in Indexly are:

- ✅ Explicit, not hidden
- ✅ Script-based and auditable
- ✅ OS-native and portable
- ✅ Logged in structured JSON
- ✅ Easy to enable and fully reversible

You stay in control — Indexly just makes it reliable.

