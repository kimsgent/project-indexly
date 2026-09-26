# Search-result terminal pagination

## Objective

Improve the interactive `indexly search` and `indexly regex` terminal experience for large result sets. Keep the complete, already-ranked result list intact; paginate **only** its human-readable terminal rendering. This is a presentation-layer change, not a search, cache, export, or profile-storage change.

## Current behavior and scope

The existing terminal renderers print every result in one stream. This is difficult to review when a query returns hundreds or thousands of matches. The renderer currently serves these paths:

- live FTS search;
- saved-profile FTS search; and
- regex search.

Apply the same paging behavior to each of those human-readable terminal paths. Preserve the existing path, tag, snippet/context, and match-highlighting treatment for every displayed item.

Do not paginate, truncate, or otherwise alter the full result collection passed to exports or saved profiles. Exported files must continue to contain all results in the same order, regardless of whether a user advances through, shows all, or quits the terminal pager.

## Required behavior

### Pagination contract

- Set the default page size to 10 results.
- If a result set contains 10 or fewer items, render it once without a navigation prompt.
- If it contains more than 10 items and the session is interactive, render page 1 first, then offer navigation after every non-final page.
- Preserve the search layer's result order exactly. Slice the already-produced list; do not rerun the query, reorder results, or fetch individual pages from the database or cache.
- Before each paged view, show the total result count and unambiguous progress, for example `Page 2 of 4 (results 11–20 of 37)`.
- Do not clear the terminal, rewrite previous output, or use cursor-control behavior. Pages must remain visible in terminal scrollback and captured interactive transcripts.

### Navigation contract

After a non-final page, present one concise prompt with these actions:

- Enter: next page.
- Space: render every remaining result without additional prompts.
- `q` (case-insensitive): stop terminal rendering.

An unrecognised response must not advance, discard, or duplicate a page. Show a short instruction and ask again. The final page must not show a prompt. Treat EOF, `KeyboardInterrupt`, and unavailable input as a clean stop to terminal paging: do not show a traceback, hang, or change the command's successful result-processing outcome.

Quitting controls only subsequent human-readable rendering. It must not cancel a completed search, change the command's exit status, prevent a requested export, or prevent a requested profile save.

### Interactive and non-interactive environments

Prompt only when both the input and output streams are attached to TTYs. Treat redirected output, piped input, CI, test capture, and unavailable standard input as non-interactive.

For a non-interactive invocation, never call `input()` or otherwise wait for user input. Preserve the current complete-output contract by rendering all results, in their existing order, without prompts; do not silently replace the output with a truncated first page. Ensure Rich/terminal configuration respects the actual output stream and does not force terminal escape sequences into redirected output.

## Architectural guidance

Keep the implementation local to the display layer. A reusable helper should accept the already-computed result sequence and a rendering callback (or equivalent shared item-rendering path), then control page boundaries and navigation. Keep the existing item rendering responsible for:

- file paths;
- tag lookup and rendering;
- snippet/context selection; and
- FTS or regex match highlighting.

Avoid duplicating the FTS and regex item-rendering rules merely to add paging. The helper should make interactive streams and input acquisition injectable or otherwise straightforward to exercise in tests. Do not introduce global mutable pagination state, cache entries, persistence, background threads, terminal-screen dependencies, or a third-party pager.

Likely implementation points are:

- [src/indexly/output_utils.py](../output_utils.py);
- [src/indexly/indexly.py](../indexly.py); and
- focused tests for terminal rendering and the existing search regression suite.

## Compatibility and invariants

The following are non-negotiable:

- Search query semantics, ranking, filtering, snippets, context length, and result ordering remain unchanged.
- FTS and regex cache reads, writes, keys, invalidation, and `--no-cache` behavior remain unchanged. The renderer must not trigger an additional search or cache operation.
- Export formats and their output files remain complete and unchanged.
- Saved-profile loading, filtering, sorting, and saving remain complete and unchanged.
- No prompt is shown for zero results, and existing no-match messages remain meaningful without duplication.
- Existing CLI options and their meaning remain compatible. Do not add a flag or change defaults outside the rendering behavior unless separately approved.
- Do not change JSON, CSV, PDF, or other export-format presentation as part of this work.

## Validation requirements

Add focused tests that verify, at minimum:

1. FTS and regex results paginate at the 10-item boundary, including 0, 10, 11, and a multi-page count.
2. Page headers report correct page and result ranges, and the full display preserves the supplied ordering.
3. Enter advances exactly one page; space prints all remaining results; `q` stops only later terminal rendering; invalid input retries the same page.
4. EOF and interrupt-like input conditions finish cleanly without a traceback or a blocking read.
5. Non-interactive streams receive all results, no prompt, and no forced terminal control sequences.
6. FTS highlighting, regex highlighting, paths, tags, and context previews are preserved on paged and unpaged views.
7. A requested export and saved-profile operation receive the complete result list even if the interactive user quits the pager.
8. Existing cache/search regression tests continue to pass, including FTS and regex cache behavior.

Run the focused display tests plus the established search controls (`tests/test_search.py`, `tests/test_delete_search.py`, and `tests/test_tagging.py`).

## Non-goals

- Changing cache formats, cache semantics, database schemas, indexing, ranking, or filtering.
- Loading results lazily from the database or storing pagination state.
- Building a full-screen pager, adding keyboard libraries, or clearing the terminal.
- Redesigning export formats or unrelated CLI output.

## Acceptance criteria

The work is complete when large interactive FTS, saved-profile FTS, and regex result sets are readable in 10-result pages; users can advance, show the remainder, or stop display predictably; non-interactive use remains complete and non-blocking; and every search, cache, export, profile, ordering, and highlighting invariant above is preserved.
