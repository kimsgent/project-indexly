---
title: "Ignore Rules & Index Hygiene"
weight: 15
type: docs
---

## Why ignore rules matter in Indexly

Semantic indexing decides **what text is meaningful enough to index**.
Ignore rules decide **which files should never be considered at all**.

Together, they form a clean indexing pipeline:

> **Ignore rules protect semantic indexing from noise before it even begins.**

Without ignore rules, semantic filtering still works — but it must process:
temporary files, caches, build artifacts, backups, and machine-generated clutter.

With ignore rules in place, Indexly never sees that noise.

----

## What Indexly ignore rules do

Ignore rules tell Indexly:

- which files or folders to **skip entirely**
- which artifacts are **never relevant to search**
- which technical byproducts should **not affect indexing performance**

They apply to:

- indexing
- semantic analysis
- database updates
- future search operations

Ignore rules are **read once**, cached internally, and enforced consistently.

----

## Ignore rule sources (priority order)

Indexly always resolves ignore rules in this order:

1. **Explicit ignore file** (CLI-provided)
2. **Project-local `.indexlyignore`**
3. **Built-in preset** (`minimal`, `standard`, `aggressive`)

Only **one source** is active at a time.

----

## Creating ignore rules (`ignore init`)

### Basic usage

```bash
indexly ignore init /path/to/project
```

Creates a `.indexlyignore` using the **standard preset**.

----

### Using a specific preset

```bash
indexly ignore init /path/to/project --preset aggressive
```

Available presets:

| **Preset**   | **Use case**               |
| ------------ | -------------------------- |
| `minimal`    | Very small projects        |
| `standard`   | Most users (default)       |
| `aggressive` | Large repos, heavy tooling |

----

### Upgrading an existing ignore file

```bash
indexly ignore init /path/to/project --upgrade
```

This safely appends **missing rules only** — nothing is overwritten.

Typical use cases:

- new Indexly version introduces new recommended rules
- project tooling changes
- pre-migration cleanup before re-indexing

----

## Example `.indexlyignore`

```other
# Python caches
__pycache__/
*.pyc

# Indexly internals
.indexly/
fts_index.db*

# Node artifacts
node_modules/
dist/
build/

# Temporary files
*.log
*.tmp
```

Only **active rules** (non-empty, non-comment lines) are applied.

----

## Inspecting ignore rules (`ignore show`)

### Basic inspection

```bash
indexly ignore show /path/to/project
```

Output:

```other
📂 Folder: /path/to/project
📄 Ignore source: project-local .indexlyignore

Active ignore rules:
  - __pycache__/
  - *.pyc
  - .indexly/
  - fts_index.db*
```

This answers:

> “What rules are currently active for this folder?”

----

## Showing rule origin (`--source`)

```bash
indexly ignore show /path/to/project --source
```

Example output:

```other
📄 Ignore source: project-local .indexlyignore
   Path: /path/to/project/.indexlyignore
```

Or, if no local file exists:

```other
📄 Ignore source: preset
   Preset: standard
```

This is especially useful **before upgrading**.

----

## Diagnostic view (`--source --verbose`)

```bash
indexly ignore show /path/to/project --source --verbose
```

Example output:

```other
📄 Ignore source: project-local .indexlyignore
   Path: /path/to/project/.indexlyignore
   Lines total: 42
   Active rules: 31
   Comments: 9
   Blank lines: 2
   Validation: OK
   Loaded via: filesystem
```

This answers:

- Is the file valid?
- How many rules are actually active?
- Is anything malformed or ignored?

👉 This is a **health check**, not a comparison.

----

## Raw view (`--source --raw`)

```bash
indexly ignore show /path/to/project --source --raw
```

Shows the **exact raw content** as read:

```other
--- RAW IGNORE FILE ---
# Company rules
.cache/
__pycache__/

# Temporary
*.tmp
*.log
----------------------
```

Use this when:

- auditing rules
- troubleshooting unexpected skips
- preparing for `--upgrade`

----

## Effective rules (`--effective`)

```bash
indexly ignore show /path/to/project --effective
```

Displays the **normalized rule set** exactly as Indexly applies it:

```other
Effective (normalized) rules:
  - *.log
  - *.tmp
  - __pycache__/
  - .indexly/
```

This view removes duplicates and ordering differences.

----

## How ignore rules support semantic indexing

Ignore rules act **before** semantic filtering.

### Pipeline overview

```other
filesystem
   ↓
ignore rules (exclude files)
   ↓
text extraction
   ↓
semantic filtering
   ↓
FTS indexing
```

This ensures that:

- semantic logic never sees junk files
- vocabularies remain clean
- indexing stays fast
- relevance remains stable at scale

----

## When to use ignore rules

Use ignore rules when:

- indexing large folders
- working with repositories
- handling build artifacts
- migrating existing databases
- preparing for semantic re-indexing

They are **safe**, **reversible**, and **non-destructive**.

----

## Preset comparison

Indexly presets are **additive by design**:

```other
minimal ⟶ standard ⟶ aggressive
```

Each higher preset **includes everything from the previous level**, plus broader exclusions.
This guarantees that `ignore init --upgrade` is **safe and predictable**.

----

### Preset overview

| **Preset**   | **Scope**    | **Philosophy**                       | **Typical use case**          |
| ------------ | ------------ | ------------------------------------ | ----------------------------- |
| `minimal`    | Indexly-only | Exclude only Indexly internals       | Small folders, personal notes |
| `standard`   | Dev-friendly | Exclude common tooling & build noise | Default for most users        |
| `aggressive` | Repo-hygiene | Exclude anything not source-like     | Large repos, monorepos        |

----

### Rule coverage comparison

| **Category**      | **Minimal** | **Standard** | **Aggressive** |
| ----------------- | ----------- | ------------ | -------------- |
| Indexly internals | ✅           | ✅            | ✅              |
| OS noise          | ❌           | ✅            | ✅              |
| Language caches   | ❌           | ✅            | ✅              |
| Build artifacts   | ❌           | ✅            | ✅              |
| Frontend tooling  | ❌           | ✅            | ✅              |
| Archives          | ❌           | ✅            | ✅              |
| Logs & temp files | ❌           | ✅            | ✅              |
| Version control   | ❌           | ✅            | ✅              |
| Package managers  | ❌           | ✅            | ✅              |

----

### What each preset contains

#### `minimal`

**Only what Indexly itself creates**

```other
.indexly/
.indexly-cache/
fts_index.db*
```

✔ Safe everywhere
✔ Never hides user files
✖ No protection against build noise

----

#### `standard` (default)

**Minimal + common development clutter**

Adds:

- OS files (`.DS_Store`, `Thumbs.db`)
- Language caches (`__pycache__`, `.pytest_cache`)
- Build outputs (`dist/`, `build/`)
- Frontend tooling (`node_modules/`)
- Logs, temp files, archives
- Version control folders

✔ Best balance of safety and cleanliness
✔ Recommended for most users

----

#### `aggressive`

**Standard + “source-only” mindset**

Focus:

- Treat repos as **code, not artifacts**
- Exclude anything machine-generated or distributable

Ideal when:

- indexing large repositories
- working with CI outputs
- re-indexing legacy projects

⚠ May exclude files some users still want indexed
⚠ Best paired with `ignore show --effective`

----

### Upgrade behavior (important)

When running:

```bash
indexly ignore init /path/to/project --upgrade
```

Indexly will:

- detect your current preset level
- append **only missing rules**
- never remove or reorder existing rules

Because presets are strictly additive, upgrades are:

✅ safe
✅ deterministic
✅ reviewable via `ignore show --source --raw`

----

👉 **Why Semantic Filtering Matters:** [What Indexly does differently](developers-why-semantic-filtering-matters.md)

* Ignore rules explain **what files never enter the system**.
* Semantic filtering explains **how remaining text is evaluated**.

Together, they explain **why Indexly search stays relevant as data grows**.