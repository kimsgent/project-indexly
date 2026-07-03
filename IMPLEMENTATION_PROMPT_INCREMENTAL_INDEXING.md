# Implementation Prompt: Incremental Indexing Feature

**Date**: 2025-07-02
**Status**: READY FOR IMPLEMENTATION
**Reference**: See [FEATURE_AUDIT_INCREMENTAL_INDEXING.md](FEATURE_AUDIT_INCREMENTAL_INDEXING.md) for complete architectural analysis and feasibility study.

---

## Overview

Implement incremental indexing with log-based filtering to dramatically improve re-indexing performance for large, stable directories. Current performance: 45 seconds for 2000 files with 5 changes. Target: <5 seconds (90% improvement).

**Backward compatible**: Default behavior unchanged. New flags are optional.
**No breaking changes**: No database schema modifications required.
**Fully feasible**: Audit confirms all infrastructure is in place.

---

## Phase 1: MVP Implementation (-r Flag Only)

### Objectives

- ✅ Reduce re-indexing time for unchanged files
- ✅ Validate log-reading strategy
- ✅ Establish foundation for Phase 2
- ✅ Maintain 100% backward compatibility

### Scope

Implement the `-r/--only-changes` flag for the `indexly index` command that:

1. Loads the most recent index log
2. Skips files marked as unchanged (`content_changed=false`)
3. Processes all new files and changed files
4. Falls back gracefully if logs are missing/corrupted

### Deliverables

#### 1. CLI Argument

**File**: `src/indexly/cli_utils.py` (line 348 in `build_parser()`)

Add argument to `index_parser`:

```python
index_parser.add_argument(
    "-r", "--only-changes",
    action="store_true",
    help="Only index files that have changed since last logged indexing run"
)
```

#### 2. LogReader Utility Module

**File**: NEW `src/indexly/incremental_indexing.py` (~150-200 lines)

Implement:

```python
class LogReader:
    """Read and filter index logs for incremental indexing."""

    def __init__(self, log_dir: Path = NDJSON_LOG_DIR):
        self.log_dir = Path(log_dir)

    def find_latest_log(self) -> Optional[Path]:
        """
        Find most recently modified log file.

        Returns:
            Path to latest log, or None if no logs found

        Notes:
            - Scans BASE_DIR/log/ recursively for .ndjson files
            - Returns most recent by modification time
        """

    def build_skip_set_from_log(
        self,
        log_path: Path,
        root_path: Optional[str] = None
    ) -> Set[str]:
        """
        Build set of normalized paths that haven't changed.

        Args:
            log_path: Path to NDJSON log file
            root_path: Optional root for path filtering

        Returns:
            Set of normalized paths where content_changed == false

        Implementation notes:
            - Use existing _parse_ndjson_records_from_path() from universal_loader.py
            - Filter for records where event == "FILE_INDEXED" AND content_changed == false
            - Normalize all paths using existing normalize_path() function
            - Return as set for O(1) lookup during file filtering
        """
```

#### 3. Integration with scan_and_index_files()

**File**: `src/indexly/indexly.py` (line 306-370 in `scan_and_index_files()`)

Modify existing function to apply filtering:

```python
# After existing file collection and ignore rules
# Before creating async tasks

if getattr(args, 'only_changes', False):
    reader = LogReader()
    latest_log = reader.find_latest_log()

    if latest_log:
        skip_set = reader.build_skip_set_from_log(latest_log, root_path=root_dir)
        file_paths = [p for p in file_paths if normalize_path(p) not in skip_set]

        if file_paths:
            print(f"📊 Filtered to {len(file_paths)} changed/new files (via -r flag)")
        else:
            print("✅ All files are up to date (via -r flag)")
    else:
        print("⚠️ No index logs found; processing all files (fallback to full index)")

# Rest of function unchanged
tasks = [async_index_file(path, ...) for path in file_paths]
```

#### 4. Unit Tests

**File**: `tests/test_incremental_indexing.py` (NEW, ~200 lines)

Minimum test coverage:

```python
def test_log_reader_finds_latest_log(tmp_path):
    """LogReader correctly identifies most recent log file"""

def test_log_reader_builds_skip_set(tmp_path):
    """LogReader correctly extracts unchanged file paths"""

def test_skip_set_ignores_changed_files(tmp_path):
    """Files with content_changed=true are NOT in skip set"""

def test_skip_set_includes_unchanged_files(tmp_path):
    """Files with content_changed=false ARE in skip set"""

def test_only_changes_flag_no_log_fallback(tmp_path, monkeypatch):
    """Fallback to full index when no logs found"""

def test_only_changes_integration_skips_files(tmp_path, monkeypatch):
    """Full integration: -r flag skips unchanged files during indexing"""

def test_backward_compatibility_no_flag(tmp_path, monkeypatch):
    """Without -r flag, behavior is identical to current"""
```

#### 5. Documentation Updates

- Update CLI help: `indexly index --help` should show new `-r` flag
- Add example to [docs/content/documentation/usage.md](docs/content/documentation/usage.md):

  ```markdown
  ## Incremental Indexing (Fast Re-indexing)

  For large directories that change infrequently, use the `-r` flag to only
  re-index files that have changed since the last run:

  ```bash
  indexly index /large/directory -r
  ```

  This can reduce re-indexing time by 80-95% for stable directories.
  Falls back to full indexing if logs are not found.

  ```

### Validation Checklist (Phase 1)

- [ ] CLI argument defined and exposed in `--help`
- [ ] LogReader module created with core methods
- [ ] `-r` flag correctly loads latest log
- [ ] Skip set building works with mixed changed/unchanged files
- [ ] Files are correctly filtered before async tasks spawn
- [ ] Fallback behavior when logs missing (processes all files)
- [ ] No changes to async_index_file() function
- [ ] No database schema modifications
- [ ] All existing tests pass without modification
- [ ] New tests pass (3 unit + 3 integration)
- [ ] Performance improvement measurable (~90% for stable dirs)
- [ ] Log format unchanged
- [ ] Backward compatible (no -r flag = original behavior)

---

## Phase 2: Extended Features (-m and -l Flags)

### Objectives (After Phase 1 Complete)

- ✅ Support month-based filtering
- ✅ Support custom log file selection
- ✅ Maintain performance gains from Phase 1
- ✅ Enable use cases: seasonal re-indexing, selective re-analysis

### Scope

Extend LogReader and CLI to support:

#### -m [month] Flag

```bash
indexly index /archive -m 07  # Only index files from July (all years)
```

#### -l [log-file] Flag

```bash
indexly index /data -l "/custom/logs/index_Q2_2025.ndjson"  # Use custom log
```

#### Combined Usage

```bash
indexly index /archive -m 03 -r  # Only changed March files
```

### Deliverables (Phase 2)

#### 1. CLI Arguments

**File**: `src/indexly/cli_utils.py`

```python
index_parser.add_argument(
    "-m", "--month",
    type=str,
    metavar="MM",
    help="Filter indexing to specified month (format: MM, e.g., 07 for July)"
)

index_parser.add_argument(
    "-l", "--log-file",
    type=str,
    metavar="PATH",
    help="Use a specific log file as the filter source (overrides -r and -m)"
)
```

#### 2. LogReader Extensions

**File**: `src/indexly/incremental_indexing.py`

Add methods:

```python
def find_logs_for_month(self, month: str) -> List[Path]:
    """
    Find all logs where entry["month"] matches specified month.

    Args:
        month: Month in MM format (01-12)

    Returns:
        List of log paths with matching month entries

    Notes:
        - Scans all BASE_DIR/log/YYYY/MM/ directories
        - Returns all matching files across all years
        - Most recent first in list
    """

def validate_custom_log_file(self, file_path: str) -> bool:
    """Validate that custom log file exists and is readable"""
```

#### 3. Integration Logic

**File**: `src/indexly/indexly.py`

Modify filter logic to handle all three flags:

```python
# Determine which logs to use
if getattr(args, 'log_file', None):
    # Custom log file takes precedence
    log_paths = [Path(args.log_file)]
elif getattr(args, 'month', None):
    # Month-based filtering
    reader = LogReader()
    log_paths = reader.find_logs_for_month(args.month)
elif getattr(args, 'only_changes', False):
    # Latest log only
    reader = LogReader()
    latest = reader.find_latest_log()
    log_paths = [latest] if latest else []
else:
    # No filtering
    log_paths = []

# Build skip set from all applicable logs
if log_paths:
    skip_set = set()
    for log_path in log_paths:
        skip_set.update(reader.build_skip_set_from_log(log_path, root_dir))

    file_paths = [p for p in file_paths if normalize_path(p) not in skip_set]
```

#### 4. Additional Tests

**File**: `tests/test_incremental_indexing.py`

Add:

```python
def test_month_filter_includes_only_matching_files():
    """Only files indexed in specified month are included"""

def test_month_filter_cross_year():
    """Month filter works across multiple years (e.g., all Julys)"""

def test_custom_log_file_validation():
    """Invalid log file path raises appropriate error"""

def test_custom_log_file_overrides_defaults():
    """Custom log file is used instead of auto-detected"""

def test_month_and_changes_combined():
    """Both -m and -r flags work together correctly"""

def test_month_no_matching_files():
    """Graceful handling when no logs found for month"""
```

### Validation Checklist (Phase 2)

- [ ] `-m` flag parses month in MM format correctly (01-12 validation)
- [ ] Month filtering scans all years correctly
- [ ] `-l` flag validates file exists before use
- [ ] Custom log file parsing works correctly
- [ ] Flag combinations work (-m -r, -l -r, etc.)
- [ ] Proper error messages for invalid inputs
- [ ] All Phase 1 tests still pass
- [ ] All new Phase 2 tests pass
- [ ] Documentation updated with examples

---

## General Implementation Guidelines

### Code Quality Standards

1. **Style**: Follow existing codebase conventions
   - Use existing import patterns
   - Match indentation and naming style
   - Include docstrings for public methods

2. **Error Handling**
   - Graceful fallbacks when logs missing/corrupted
   - Clear error messages for user mistakes
   - Log warnings for degraded modes

3. **Performance**
   - O(n) parsing of logs (where n = log entries)
   - O(1) skip set lookup during file filtering
   - Minimal overhead when -r flag not used

4. **Testing**
   - Unit tests for LogReader class
   - Integration tests with handle_index()
   - Regression tests (ensure backward compatibility)
   - Edge case coverage

5. **Documentation**
   - Docstrings for all public functions
   - Inline comments for complex logic
   - Update CLI help text
   - Add usage examples to user guide

### Reusable Components (Already in Codebase)

Do NOT reinvent these - reuse existing:

| Component | Location | Use For |
|-----------|----------|---------|
| `_parse_ndjson_records_from_path()` | `universal_loader.py:215` | Parse NDJSON log files |
| `normalize_path()` | `path_utils.py` | Normalize paths for comparison |
| `NDJSON_LOG_DIR` | `log_utils.py:53` | Get log directory |
| `SUPPORTED_EXTENSIONS` | `indexly.py` | File type filtering |

### Key Files to Reference

- **Current indexing**: `src/indexly/indexly.py` (handle_index, scan_and_index_files)
- **CLI setup**: `src/indexly/cli_utils.py` (build_parser)
- **Log format**: `src/indexly/log_utils.py` (LogManager, _unified_log_entry)
- **Existing tests**: `tests/test_*_index*.py` (for patterns)

---

## Integration Checklist

Before marking implementation complete:

### Phase 1 Completion

- [ ] Branch: `feature/incremental-indexing`
- [ ] Commits are atomic and well-documented
- [ ] All tests passing locally: `pytest tests/test_incremental_indexing.py`
- [ ] All existing tests still pass: `pytest tests/`
- [ ] Performance verified with benchmark (2000 files test case)
- [ ] Code review checklist complete
- [ ] Documentation updated
- [ ] Ready for merge to staging

### Phase 2 Completion (Optional, after Phase 1 approved)

- [ ] Same checklist repeated
- [ ] Additional tests for -m and -l flags
- [ ] Cross-team documentation review
- [ ] Beta testing with real large directories

---

## Success Criteria

### Functional

- ✅ `-r` flag works correctly (Phase 1)
- ✅ Falls back to full index when logs missing
- ✅ Default behavior (no flags) unchanged
- ✅ `-m` and `-l` flags work (Phase 2)

### Performance

- ✅ 2000 files with 5 changes: <5 seconds (target 90% improvement)
- ✅ No regression for default behavior (no flags)
- ✅ Log parsing overhead <100ms

### Quality

- ✅ All tests passing (new + existing)
- ✅ Code review approved
- ✅ No breaking changes
- ✅ Backward compatible

### Documentation

- ✅ CLI help text updated
- ✅ Usage guide examples added
- ✅ Code comments adequate
- ✅ Edge cases documented

---

## References

For complete architectural context, design decisions, and feasibility analysis, see:
**[FEATURE_AUDIT_INCREMENTAL_INDEXING.md](FEATURE_AUDIT_INCREMENTAL_INDEXING.md)**

This audit contains:

- Part 1: Current Architecture Analysis (flow diagrams, log structure)
- Part 2: Feature Specification (all command variants)
- Part 3: Technical Feasibility Analysis (confirms all is feasible)
- Part 4: Implementation Approach (pseudocode examples)
- Part 5: Limitations & Constraints (edge cases)
- Part 6: Quality Assurance Strategy
- Part 7: Professional Recommendation (HIGH confidence)

---

**Implementation Status**: READY TO BEGIN
**Confidence Level**: HIGH (95%)
**Estimated Total Effort**: 6-8 hours (Phase 1 + Phase 2)

Begin with Phase 1. Phase 2 can wait for Phase 1 approval and integration.

---

## 2026-07-03 Implementation Addendum: Correctness-First Phase 1

The original Phase 1 pseudocode proposed skipping files purely when the latest
index log says `content_changed=false`. Do **not** implement that literally.
A past `content_changed=false` record only proves the file was unchanged during
that previous run. If a user edits the file after the log is written, a log-only
skip set would incorrectly skip the changed file and leave the search index
stale.

### Updated Phase 1 Recommendation

Implement `-r/--only-changes` as a safe incremental re-index mode using current
filesystem state and existing database state as the source of truth:

1. Collect supported, non-ignored files exactly as today.
2. Preserve the full collected file list for stale-row pruning.
3. For `-r`, query `file_index` for existing `path` and `modified` values.
4. Compare each current file's `mtime` with the stored `file_index.modified`.
5. Process files that are new, missing DB metadata, unreadable during the quick
   check, or whose `mtime` changed.
6. Skip only files whose current normalized path exists in `file_index` and whose
   current `mtime` matches the stored `modified` value.
7. Keep the existing content-hash comparison inside `async_index_file()` as the
   final content-change authority for files that are processed.
8. Bump `search_index_generation` only when processed files actually change
   content or stale rows are pruned, matching the existing cache contract.

Logs may still be parsed by a `LogReader` utility for future Phase 2 work and
for diagnostics, but logs must not be the only freshness source for Phase 1.

### Required Extra Regressions

- A file previously logged as unchanged but edited after the log must still be
  processed by `-r`.
- `-r` must not pass the filtered list into stale-row pruning; ignored or deleted
  files should still be pruned based on the full current scan set.
- An all-up-to-date `-r` run should skip async indexing work and avoid bumping
  `search_index_generation`.
- Default indexing without `-r` must behave exactly as before.

### Updated Phase 2 Recommendation

Implement `-m/--month` and `-l/--log-file` as **scope selectors**, not freshness
signals:

1. `--month MM` discovers NDJSON logs containing `FILE_INDEXED` entries whose
   `month` field equals `MM`, then limits indexing to currently scanned files
   that appear in those matching log records.
2. `--log-file PATH` uses that specific NDJSON file as the scope source and
   fails clearly if the file does not exist, is unreadable, or cannot be parsed.
3. If `--log-file` and `--month` are combined, the custom log remains the source
   and `--month` filters records within that log.
4. If `--month` finds no matching logs, fall back to the full current scan with
   a warning, matching the original forgiving auto-discovery behavior.
5. If `-r` is also provided, apply the safe mtime/DB incremental filter after
   the log/month scope has been applied.
6. Always keep stale-row pruning based on the full supported, non-ignored current
   scan set, never the scoped or `-r`-filtered task list.

---

## 2026-07-03 Phase 3 Recommendation: Observability and Plan Mode

Phase 3 is an implementation recommendation added after Phases 1 and 2 proved
useful in real indexing workflows. It was not part of the original prompt, but
it is the next low-risk extension because it improves trust, debuggability, and
performance visibility without changing the indexing schema.

### Phase 3 Scope

1. Add richer `INDEX_SUMMARY` fields for incremental and scoped runs:
   - `mode`: `full`, `only_changes`, `month`, `log_file`, or combined labels.
   - `scanned_count`: supported, non-ignored files discovered in the current scan.
   - `scoped_count`: files remaining after `--month` / `--log-file` scope filters.
   - `skipped_unchanged_count`: files skipped by `-r`.
   - `indexed_count`: files actually sent to indexing tasks.
   - `changed_count`: files whose indexed content changed.
   - `removed_count`: stale search-index rows pruned.
   - `stat_error_count`: files indexed because the fast stat check could not read
     them.
2. Add `--plan` for `indexly index`:
   - Shows the same scan/scope/skip/prune metrics without indexing files.
   - Does not spawn `async_index_file()`.
   - Does not prune stale rows.
   - Does not write index log entries or summaries.
   - Still validates user inputs such as invalid `--month` or `--log-file`.
3. Add focused tests:
   - Plan mode reports index candidates and stale prune candidates without DB/log
     writes.
   - Plan mode honors `-r`, `--month`, and `--log-file` composition.
   - Summary entries include the new metrics during real runs.
   - A performance-style regression verifies `-r` avoids extraction/index calls
     for many unchanged files. Avoid brittle wall-clock assertions.
4. Update user documentation with a practical mode guide:
   - normal full index
   - `-r` fast re-index
   - `--month`
   - `--month -r`
   - `--log-file`
   - `--plan`

### Phase 4 Recommendation: Persistent Stat Fingerprints

After Phase 3, the next performance and robustness improvement should be a
persistent stat fingerprint for each indexed file. Current `-r` uses
`file_index.modified`, which is fast and works well, but it relies on timestamp
precision and can miss unusual cases such as copied files that preserve mtimes,
filesystems with coarse timestamp resolution, or tools that rewrite content
while restoring the old modified time.

Recommended design:

1. Add a small metadata payload, preferably in `file_metadata.metadata`, rather
   than changing the FTS schema:
   - `stat_mtime_ns`: `Path.stat().st_mtime_ns`
   - `stat_size`: `Path.stat().st_size`
   - `stat_inode`: `st_ino` where available
   - `stat_device`: `st_dev` where available
   - `stat_fingerprint_version`: integer, starting at `1`
2. During indexing, persist the stat fingerprint alongside existing metadata.
3. During `-r`, skip only when the stored fingerprint matches the current
   fingerprint. Fall back to the existing mtime behavior when no fingerprint is
   present so older indexes remain compatible.
4. Add an opt-in repair command or passive migration path:
   - passive: fingerprint appears naturally as files are re-indexed
   - optional future command: `indexly index /path --refresh-stat-cache`
5. Add regressions:
   - same mtime but different size is processed
   - same mtime and same size remains skipped
   - missing fingerprint falls back to current mtime logic
   - stat errors index the file instead of skipping it
6. Keep no schema migration mandatory unless a future design proves a dedicated
   table is materially cleaner.

### 2026-07-03 Phase 4 Implementation Notes

Implemented the passive stat fingerprint path without a schema migration:

1. Real indexing writes persist `stat_fingerprint_version`, `stat_mtime_ns`,
   `stat_size`, `stat_inode`, and `stat_device` into `file_metadata.metadata`.
2. `-r` prefers an exact stat fingerprint match when metadata is present.
3. Legacy rows with no fingerprint fall back to the existing `file_index.modified`
   timestamp comparison.
4. Files that cannot be statted by the fast path are indexed rather than skipped.
5. The fingerprint is populated passively whenever a file is re-indexed; no
   forced rebuild is required for existing indexes.

Deferred follow-up:

- Consider `indexly index /path --refresh-stat-cache` if users need to populate
  fingerprints for old indexes without re-extracting file contents. This should
  be designed carefully because it would update metadata without refreshing FTS
  content.
