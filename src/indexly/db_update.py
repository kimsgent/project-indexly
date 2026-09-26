"""Database schema inspection and safe FTS5 repair helpers."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Literal


@dataclass(frozen=True)
class FTS5Definition:
    """The authoritative semantic definition of an Indexly FTS5 table."""

    module: str
    columns: tuple[str, ...]
    tokenizer: tuple[str, ...]
    prefix: tuple[int, ...]
    options: tuple[tuple[str, str], ...] = ()


FILE_INDEX_FTS_SPEC = FTS5Definition(
    module="fts5",
    columns=("path", "content", "clean_content", "modified", "hash", "tag"),
    tokenizer=("porter",),
    prefix=(2, 3, 4),
)

EXPECTED_SCHEMA = {
    "file_index": """
        CREATE VIRTUAL TABLE file_index USING fts5(
            path,
            content,
            clean_content,
            modified,
            hash,
            tag,
            tokenize='porter',
            prefix='2 3 4'
        );
    """,
    "file_metadata": """
        CREATE TABLE IF NOT EXISTS file_metadata (
            path TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            subject TEXT,
            created TEXT,
            last_modified TEXT,
            last_modified_by TEXT,
            alias TEXT,
            camera TEXT,
            image_created TEXT,
            dimensions TEXT,
            format TEXT,
            gps TEXT,
            metadata TEXT
        );
    """,
    "file_tags": """
        CREATE TABLE IF NOT EXISTS file_tags (
            path TEXT PRIMARY KEY,
            tags TEXT
        );
    """,
}

_SUPPORTED_FTS5_OPTIONS = {
    "columnsize",
    "content",
    "contentless_delete",
    "contentless_unindexed",
    "content_rowid",
    "detail",
    "locale",
    "prefix",
    "tokendata",
    "tokenize",
}


class FTS5InspectionError(ValueError):
    """Raised when a CREATE statement cannot be inspected safely."""


class FTS5RebuildError(RuntimeError):
    """Raised when an FTS5 rebuild cannot be completed and verified."""

    def __init__(self, message: str, *, snapshot_path: Path | None = None):
        super().__init__(message)
        self.snapshot_path = snapshot_path


@dataclass(frozen=True)
class FTS5Inspection:
    state: Literal["match", "drift", "uninspectable"]
    reason: str
    definition: FTS5Definition | None = None


@dataclass(frozen=True)
class FTS5RebuildResult:
    rows_preserved: int
    generation: int
    snapshot_path: Path


def _split_top_level(value: str, separator: str = ",") -> list[str]:
    """Split SQL only at unquoted, top-level separators."""

    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    index = 0
    while index < len(value):
        char = value[index]
        if quote:
            if quote == "]":
                if char == "]":
                    quote = None
            elif char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "[":
            quote = "]"
        elif char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                raise FTS5InspectionError("unbalanced closing parenthesis")
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
        index += 1
    if quote or depth:
        raise FTS5InspectionError("unterminated quote or parenthesis")
    parts.append(value[start:].strip())
    return parts


def _find_top_level(value: str, needle: str) -> int:
    """Return an unquoted top-level character position, or ``-1``."""

    depth = 0
    quote: str | None = None
    index = 0
    while index < len(value):
        char = value[index]
        if quote:
            if quote == "]" and char == "]":
                quote = None
            elif quote != "]" and char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "[":
            quote = "]"
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise FTS5InspectionError("unbalanced closing parenthesis")
        elif char == needle and depth == 0:
            return index
        index += 1
    if quote or depth:
        raise FTS5InspectionError("unterminated quote or parenthesis")
    return -1


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) < 2:
        return value
    pairs = {"'": "'", '"': '"', "`": "`", "[": "]"}
    end = pairs.get(value[0])
    if end and value[-1] == end:
        inner = value[1:-1]
        return inner.replace(end * 2, end) if end != "]" else inner
    return value


def _identifier(value: str) -> str:
    token = value.strip()
    if not token:
        raise FTS5InspectionError("missing identifier")
    if token[0] in {'"', "`", "["}:
        end = "]" if token[0] == "[" else token[0]
        close = token.find(end, 1)
        if close < 0 or token[close + 1 :].strip():
            raise FTS5InspectionError("malformed quoted identifier")
        token = _unquote(token)
    elif any(char.isspace() for char in token):
        raise FTS5InspectionError("unsupported FTS5 column constraint")
    return token.casefold()


def _column_definition(value: str) -> tuple[str, str | None]:
    """Parse an FTS5 user-column name and its optional UNINDEXED marker."""

    text = value.strip()
    if not text:
        raise FTS5InspectionError("missing FTS5 column")
    if text[0] in {'"', "`", "["}:
        end = "]" if text[0] == "[" else text[0]
        index = 1
        while index < len(text):
            if text[index] == end:
                if end != "]" and index + 1 < len(text) and text[index + 1] == end:
                    index += 2
                    continue
                break
            index += 1
        if index >= len(text):
            raise FTS5InspectionError("malformed quoted FTS5 column")
        name_text = text[: index + 1]
        remainder = text[index + 1 :].strip()
    else:
        pieces = text.split(maxsplit=1)
        name_text = pieces[0]
        remainder = pieces[1].strip() if len(pieces) == 2 else ""
    column = _identifier(name_text)
    if not remainder:
        return column, None
    if remainder.casefold() == "unindexed":
        return column, "unindexed"
    raise FTS5InspectionError("unsupported FTS5 column constraint")


def _token_sequence(value: str) -> tuple[str, ...]:
    raw = _unquote(value)
    tokens: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if quote:
            if char == quote:
                if index + 1 < len(raw) and raw[index + 1] == quote:
                    current.append(char)
                    index += 1
                else:
                    quote = None
            else:
                current.append(char)
        elif char in {"'", '"'}:
            quote = char
        elif char.isspace():
            if current:
                tokens.append("".join(current).casefold())
                current = []
        else:
            current.append(char)
        index += 1
    if quote:
        raise FTS5InspectionError("unterminated tokenizer quote")
    if current:
        tokens.append("".join(current).casefold())
    if not tokens:
        raise FTS5InspectionError("empty tokenizer")
    return tuple(tokens)


def _prefix_sequence(value: str) -> tuple[int, ...]:
    raw = _unquote(value).replace(",", " ")
    try:
        prefix = tuple(int(token) for token in raw.split())
    except ValueError as exc:
        raise FTS5InspectionError("prefix values must be integers") from exc
    if not prefix or any(item <= 0 for item in prefix):
        raise FTS5InspectionError("prefix values must be positive")
    return prefix


def _create_virtual_parts(sql: str) -> tuple[str, str]:
    """Return ``(module, argument body)`` for CREATE VIRTUAL TABLE SQL."""

    text = sql.strip().rstrip(";").strip()
    words = text.casefold().split()
    if len(words) < 6 or words[:3] != ["create", "virtual", "table"]:
        raise FTS5InspectionError("not a CREATE VIRTUAL TABLE statement")

    depth = 0
    quote: str | None = None
    opening = -1
    closing = -1
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if quote == "]" and char == "]":
                if index + 1 < len(text) and text[index + 1] == "]":
                    index += 1
                else:
                    quote = None
            elif quote != "]" and char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "[":
            quote = "]"
        elif char == "(":
            if depth == 0:
                opening = index
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                closing = index
            if depth < 0:
                raise FTS5InspectionError("unbalanced closing parenthesis")
        index += 1
    if quote or depth or opening < 0 or closing < opening:
        raise FTS5InspectionError("malformed virtual table argument list")
    if text[closing + 1 :].strip():
        raise FTS5InspectionError("unexpected SQL after virtual table definition")

    before = text[:opening].strip()
    before_words = before.split()
    using_positions = [
        index for index, word in enumerate(before_words) if word.casefold() == "using"
    ]
    if len(using_positions) != 1 or using_positions[0] != len(before_words) - 2:
        raise FTS5InspectionError("malformed USING clause")
    return _identifier(before_words[-1]), text[opening + 1 : closing]


def parse_fts5_definition(sql: str) -> FTS5Definition:
    """Parse an FTS5 CREATE statement without relying on comma splitting."""

    if not sql:
        raise FTS5InspectionError("missing CREATE SQL")
    module, body = _create_virtual_parts(sql)
    columns: list[str] = []
    tokenizer: tuple[str, ...] | None = None
    prefixes: list[int] = []
    options: dict[str, str] = {}

    for part in _split_top_level(body):
        if not part:
            raise FTS5InspectionError("empty FTS5 argument")
        equals = _find_top_level(part, "=")
        if equals < 0:
            column, column_option = _column_definition(part)
            columns.append(column)
            if column_option:
                options[f"column:{column}"] = column_option
            continue
        name = _identifier(part[:equals])
        value = part[equals + 1 :].strip()
        if not value or name not in _SUPPORTED_FTS5_OPTIONS:
            raise FTS5InspectionError(f"unsupported FTS5 option: {name}")
        if name == "tokenize":
            if tokenizer is not None:
                raise FTS5InspectionError("duplicate tokenize option")
            tokenizer = _token_sequence(value)
        elif name == "prefix":
            prefixes.extend(_prefix_sequence(value))
        else:
            normalized = _unquote(value).strip().casefold()
            if name in options and options[name] != normalized:
                raise FTS5InspectionError(f"conflicting {name} options")
            options[name] = normalized

    if not columns:
        raise FTS5InspectionError("FTS5 definition has no user columns")
    return FTS5Definition(
        module=module,
        columns=tuple(columns),
        tokenizer=tokenizer or ("unicode61",),
        prefix=tuple(sorted(set(prefixes))),
        options=tuple(sorted(options.items())),
    )


def inspect_fts5_definition(
    sql: str | None, expected: FTS5Definition = FILE_INDEX_FTS_SPEC
) -> FTS5Inspection:
    """Classify SQL as a semantic match, drift, or uninspectable."""

    try:
        actual = parse_fts5_definition(sql or "")
    except FTS5InspectionError as exc:
        return FTS5Inspection("uninspectable", str(exc))

    mismatches = []
    for field in ("module", "columns", "tokenizer", "prefix", "options"):
        if getattr(actual, field) != getattr(expected, field):
            mismatches.append(field)
    if mismatches:
        return FTS5Inspection(
            "drift", f"FTS5 definition mismatch: {', '.join(mismatches)}", actual
        )
    return FTS5Inspection("match", "FTS5 definition matches", actual)


def _extract_columns_from_sql(sql: str) -> list[str]:
    """Compatibility helper backed by structured FTS inspection where possible."""

    try:
        return list(parse_fts5_definition(sql).columns)
    except FTS5InspectionError:
        # Normal tables remain simple and are not used for option validation.
        opening = sql.find("(")
        closing = sql.rfind(")")
        if opening < 0 or closing <= opening:
            return []
        try:
            parts = _split_top_level(sql[opening + 1 : closing])
        except FTS5InspectionError:
            return []
        columns = []
        for part in parts:
            first = part.strip().split(maxsplit=1)
            if first and first[0].casefold() not in {
                "constraint",
                "primary",
                "unique",
                "foreign",
                "check",
            }:
                columns.append(_unquote(first[0]).casefold())
        return columns


def _get_existing_schema(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT name, sql FROM sqlite_master
        WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
        """
    )
    return {row[0]: row[1] for row in rows if row[1]}


def check_schema(conn: sqlite3.Connection, verbose: bool = True):
    """Compare the database against Indexly's authoritative schema."""

    existing = _get_existing_schema(conn)
    diffs = []
    for table, expected_sql in EXPECTED_SCHEMA.items():
        expected_cols = _extract_columns_from_sql(expected_sql)
        current_sql = existing.get(table)
        if not current_sql:
            diffs.append((table, "Missing table", expected_cols))
            continue
        if table == "file_index":
            inspection = inspect_fts5_definition(current_sql)
            if inspection.state == "drift":
                diffs.append((table, f"FTS5 rebuild needed ({inspection.reason})", []))
            elif inspection.state == "uninspectable":
                diffs.append((table, f"FTS5 definition uninspectable ({inspection.reason})", []))
            continue
        current_cols = _extract_columns_from_sql(current_sql)
        missing_cols = [column for column in expected_cols if column not in current_cols]
        if missing_cols:
            diffs.append(
                (table, f"ALTER TABLE needed (missing {missing_cols})", missing_cols)
            )

    if verbose:
        print("🔍 Checking schema differences...")
        if not diffs:
            print("✅ All tables match expected schema.")
        for table, message, _ in diffs:
            print(f"⚠️  {table}: {message}")
    return diffs


def _database_path(conn: sqlite3.Connection) -> Path:
    row = conn.execute("PRAGMA database_list").fetchone()
    if not row or not row[2]:
        raise FTS5RebuildError("FTS5 rebuild requires a file-backed database")
    return Path(row[2]).resolve()


def _integrity_ok(conn: sqlite3.Connection) -> bool:
    return all(row[0] == "ok" for row in conn.execute("PRAGMA integrity_check"))


def _verify_writable_directory(directory: Path) -> None:
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".indexly-write-", delete=True):
            pass
    except OSError as exc:
        raise FTS5RebuildError(f"database directory is not writable: {directory}") from exc


def _required_workspace_bytes(
    conn: sqlite3.Connection,
    db_path: Path,
) -> int:
    """Estimate free workspace from the logical DB, including committed WAL pages."""
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    logical_bytes = max(page_count * page_size, db_path.stat().st_size)
    sidecar_bytes = sum(
        path.stat().st_size
        for suffix in ("-wal", "-shm", "-journal")
        if (path := Path(f"{db_path}{suffix}")).is_file()
    )
    # Snapshot + replacement/shadow tables + bounded SQLite temporary-sort margin,
    # with current sidecars counted once as an additional conservative reserve.
    return max(logical_bytes * 3 + sidecar_bytes, 1 << 20)


def _verify_free_space(conn: sqlite3.Connection, db_path: Path) -> None:
    required = _required_workspace_bytes(conn, db_path)
    available = shutil.disk_usage(db_path.parent).free
    if available < required:
        raise FTS5RebuildError(
            f"insufficient free space: need {required} bytes, have {available} bytes"
        )


def _snapshot_path(db_path: Path) -> Path:
    directory = db_path.parent / "backups"
    directory.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return directory / f"{db_path.stem}_fts_snapshot_{stamp}_{uuid.uuid4().hex[:8]}.sqlite"


def _create_verified_snapshot(
    db_path: Path,
    source_inspection: FTS5Inspection,
) -> Path:
    snapshot_path = _snapshot_path(db_path)
    source = sqlite3.connect(db_path)
    snapshot = sqlite3.connect(snapshot_path)
    try:
        source.backup(snapshot)
        if not _integrity_ok(snapshot):
            raise FTS5RebuildError("snapshot failed SQLite integrity verification")
        row = snapshot.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='file_index'"
        ).fetchone()
        inspection = inspect_fts5_definition(row[0] if row else None)
        if (
            inspection.state != source_inspection.state
            or inspection.definition != source_inspection.definition
        ):
            raise FTS5RebuildError("snapshot schema does not match the source database")
    except Exception:
        source.close()
        snapshot.close()
        snapshot_path.unlink(missing_ok=True)
        raise
    source.close()
    snapshot.close()
    return snapshot_path


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _logical_digest(
    conn: sqlite3.Connection,
    table: str,
    columns: Iterable[str],
    *,
    batch_size: int = 512,
) -> str:
    """Digest logical rows in fixed-size batches, preserving SQLite value types."""

    quoted = ", ".join(_quote_identifier(column) for column in columns)
    cursor = conn.execute(
        f"SELECT rowid, {quoted} FROM {_quote_identifier(table)} ORDER BY rowid"
    )
    digest = hashlib.sha256()
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for row in rows:
            for value in row:
                if value is None:
                    payload = b"N"
                elif isinstance(value, bytes):
                    payload = b"B" + value
                elif isinstance(value, int):
                    payload = b"I" + str(value).encode("ascii")
                elif isinstance(value, float):
                    payload = b"F" + value.hex().encode("ascii")
                else:
                    payload = b"T" + str(value).encode("utf-8", "surrogatepass")
                digest.update(len(payload).to_bytes(8, "big"))
                digest.update(payload)
    return digest.hexdigest()


def _row_metrics(conn: sqlite3.Connection, table: str) -> tuple[int, int, int, int]:
    quoted = _quote_identifier(table)
    return tuple(
        conn.execute(
            f"""
            SELECT
                COUNT(*),
                SUM(CASE WHEN path IS NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN path IS NOT NULL AND trim(path) = '' THEN 1 ELSE 0 END),
                (
                    SELECT COUNT(*) FROM (
                        SELECT path FROM {quoted}
                        WHERE path IS NOT NULL
                        GROUP BY path HAVING COUNT(*) > 1
                    )
                )
            FROM {quoted}
            """
        ).fetchone()
    )


def _create_fts_sql(table: str) -> str:
    columns = ", ".join(_quote_identifier(column) for column in FILE_INDEX_FTS_SPEC.columns)
    tokenizer = " ".join(FILE_INDEX_FTS_SPEC.tokenizer).replace("'", "''")
    prefix = " ".join(str(item) for item in FILE_INDEX_FTS_SPEC.prefix)
    option_parts = []
    for name, value in FILE_INDEX_FTS_SPEC.options:
        escaped_value = value.replace("'", "''")
        option_parts.append(f", {_quote_identifier(name)}='{escaped_value}'")
    options = "".join(option_parts)
    return (
        f"CREATE VIRTUAL TABLE {_quote_identifier(table)} USING fts5("
        f"{columns}, tokenize='{tokenizer}', prefix='{prefix}'{options})"
    )


def _bump_generation_in_transaction(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS indexly_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    row = conn.execute(
        "SELECT value FROM indexly_state WHERE key='search_index_generation'"
    ).fetchone()
    try:
        current = int(row[0]) if row else 0
    except (TypeError, ValueError):
        current = 0
    generation = current + 1
    conn.execute(
        """
        INSERT INTO indexly_state(key, value)
        VALUES ('search_index_generation', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (str(generation),),
    )
    return generation


def _verify_vocab_and_match(
    conn: sqlite3.Connection, table: str, vocab_table: str
) -> None:
    conn.execute(
        f"CREATE VIRTUAL TABLE {_quote_identifier(vocab_table)} "
        f"USING fts5vocab({_quote_identifier(table)}, 'row')"
    )
    term_row = conn.execute(
        f"SELECT term FROM {_quote_identifier(vocab_table)} ORDER BY term LIMIT 1"
    ).fetchone()
    total = conn.execute(
        f"SELECT COUNT(*) FROM {_quote_identifier(table)}"
    ).fetchone()[0]
    if total and not term_row:
        raise FTS5RebuildError("replacement vocabulary is unavailable")
    if term_row:
        matched = conn.execute(
            f"SELECT 1 FROM {_quote_identifier(table)} "
            f"WHERE {_quote_identifier(table)} MATCH ? LIMIT 1",
            (term_row[0],),
        ).fetchone()
        if not matched:
            raise FTS5RebuildError("representative MATCH verification failed")


def _rebuild_fts5_table(
    conn: sqlite3.Connection,
    table_name: str,
    expected_sql: str | None = None,
    db_path: Path | None = None,
) -> FTS5RebuildResult:
    """Rebuild ``file_index`` transactionally with a verified SQLite snapshot."""

    if table_name != "file_index":
        raise FTS5RebuildError("only the authoritative file_index table can be rebuilt")
    actual_path = _database_path(conn)
    if db_path is not None and Path(db_path).resolve() != actual_path:
        raise FTS5RebuildError("database path does not match the open connection")
    if conn.in_transaction:
        raise FTS5RebuildError("FTS5 rebuild requires a connection with no active transaction")

    sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    inspection = inspect_fts5_definition(sql_row[0] if sql_row else None)
    if inspection.state == "uninspectable":
        raise FTS5RebuildError(f"refusing uninspectable FTS5 schema: {inspection.reason}")
    if not _integrity_ok(conn):
        raise FTS5RebuildError("database failed full integrity preflight")
    _verify_writable_directory(actual_path.parent)
    _verify_free_space(conn, actual_path)

    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        raise FTS5RebuildError("could not acquire the exclusive-writer lock") from exc

    snapshot_path: Path | None = None
    try:
        snapshot_path = _create_verified_snapshot(actual_path, inspection)
        suffix = uuid.uuid4().hex
        replacement = f"file_index_replacement_{suffix}"
        replacement_vocab = f"{replacement}_vocab"
        old_table = f"file_index_retired_{suffix}"
        common_columns = [
            column
            for column in FILE_INDEX_FTS_SPEC.columns
            if column in (inspection.definition.columns if inspection.definition else ())
        ]
        if "path" not in common_columns:
            raise FTS5RebuildError("source FTS5 table has no inspectable path column")

        source_metrics = _row_metrics(conn, table_name)
        if source_metrics[1] or source_metrics[2] or source_metrics[3]:
            raise FTS5RebuildError(
                "source rows contain null, empty, or duplicate paths"
            )
        source_digest = _logical_digest(conn, table_name, common_columns)

        conn.execute("SAVEPOINT indexly_fts_rebuild")
        conn.execute(_create_fts_sql(replacement))
        quoted_columns = ", ".join(
            _quote_identifier(column) for column in common_columns
        )
        conn.execute(
            f"INSERT INTO {_quote_identifier(replacement)}(rowid, {quoted_columns}) "
            f"SELECT rowid, {quoted_columns} FROM {_quote_identifier(table_name)}"
        )

        replacement_metrics = _row_metrics(conn, replacement)
        replacement_digest = _logical_digest(conn, replacement, common_columns)
        if replacement_metrics != source_metrics or replacement_digest != source_digest:
            raise FTS5RebuildError("replacement logical-row verification failed")
        replacement_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (replacement,),
        ).fetchone()
        if (
            inspect_fts5_definition(replacement_sql[0] if replacement_sql else None).state
            != "match"
        ):
            raise FTS5RebuildError("replacement FTS5 definition verification failed")
        _verify_vocab_and_match(conn, replacement, replacement_vocab)

        conn.execute("DROP TABLE IF EXISTS file_index_vocab")
        conn.execute(f"DROP TABLE {_quote_identifier(replacement_vocab)}")
        conn.execute(
            f"ALTER TABLE {_quote_identifier(table_name)} "
            f"RENAME TO {_quote_identifier(old_table)}"
        )
        conn.execute(
            f"ALTER TABLE {_quote_identifier(replacement)} "
            f"RENAME TO {_quote_identifier(table_name)}"
        )
        conn.execute(f"DROP TABLE {_quote_identifier(old_table)}")
        conn.execute(
            "CREATE VIRTUAL TABLE file_index_vocab "
            "USING fts5vocab(file_index, 'row')"
        )
        _verify_vocab_and_match(conn, table_name, f"file_index_verify_{suffix}")
        conn.execute(f"DROP TABLE {_quote_identifier(f'file_index_verify_{suffix}')}")
        generation = _bump_generation_in_transaction(conn)
        conn.execute("RELEASE SAVEPOINT indexly_fts_rebuild")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if isinstance(exc, FTS5RebuildError):
            if exc.snapshot_path is None:
                exc.snapshot_path = snapshot_path
            raise
        raise FTS5RebuildError(
            f"FTS5 rebuild failed and was rolled back: {exc}",
            snapshot_path=snapshot_path,
        ) from exc

    try:
        final = sqlite3.connect(actual_path)
        try:
            if not _integrity_ok(final):
                raise FTS5RebuildError("final database failed integrity verification")
            final_sql = final.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='file_index'"
            ).fetchone()
            if inspect_fts5_definition(final_sql[0] if final_sql else None).state != "match":
                raise FTS5RebuildError("final FTS5 definition verification failed")
            if _row_metrics(final, table_name) != source_metrics:
                raise FTS5RebuildError("final logical-row metrics verification failed")
            if _logical_digest(final, table_name, common_columns) != source_digest:
                raise FTS5RebuildError("final logical-row digest verification failed")
            final.execute("SELECT 1 FROM file_index_vocab LIMIT 1").fetchone()
        finally:
            final.close()
    except Exception as exc:
        raise FTS5RebuildError(
            f"post-commit verification failed; recover from snapshot {snapshot_path}: {exc}",
            snapshot_path=snapshot_path,
        ) from exc

    print(
        f"  ✅ Rebuilt FTS5 table '{table_name}' with {source_metrics[0]} rows; "
        f"snapshot: {snapshot_path}"
    )
    return FTS5RebuildResult(source_metrics[0], generation, snapshot_path)


def _backup_database(conn: sqlite3.Connection) -> Path:
    """Create and verify a SQLite-consistent backup of the open database."""

    db_path = _database_path(conn)
    inspection_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='file_index'"
    ).fetchone()
    inspection = inspect_fts5_definition(inspection_row[0] if inspection_row else None)
    backup = _create_verified_snapshot(db_path, inspection)
    print(f"🗂️ Backup created: {backup}")
    return backup


def apply_migrations(
    conn: sqlite3.Connection,
    dry_run: bool = False,
    auto_fix: bool = False,
    allow_fts_rebuild: bool = False,
):
    """Apply schema changes, requiring explicit authorization for FTS rebuilds."""

    diffs = check_schema(conn, verbose=False)
    if not diffs:
        print("✅ No schema updates needed.")
        return
    print("\n🚧 Schema differences detected:")
    for table, message, _ in diffs:
        print(f"  • {table}: {message}")
    if dry_run:
        print("\n💡 Dry-run: No changes applied. Use --apply to perform migrations.")
        return

    non_fts_changes = [
        diff for diff in diffs if not diff[1].startswith("FTS5")
    ]
    if non_fts_changes:
        _backup_database(conn)

    for table, message, missing_columns in diffs:
        print(f"\n🔧 Updating {table}: {message}")
        if message.startswith("FTS5 definition uninspectable"):
            raise FTS5RebuildError(
                "refusing automatic repair of an uninspectable FTS5 definition"
            )
        if message.startswith("FTS5 rebuild needed"):
            if not allow_fts_rebuild:
                print(
                    "  ⏭️ Skipping FTS5 rebuild; use "
                    "`indexly doctor --fix-db --rebuild-fts` for explicit repair."
                )
                continue
            if not auto_fix:
                answer = input(
                    "Proceed with verified, snapshot-backed FTS rebuild? (y/N): "
                ).strip().casefold()
                if answer != "y":
                    print(f"🚫 Skipping rebuild of {table} by user choice.")
                    continue
            _rebuild_fts5_table(conn, table, EXPECTED_SCHEMA[table])
        elif message.startswith("ALTER"):
            for column in missing_columns:
                conn.execute(
                    f"ALTER TABLE {_quote_identifier(table)} "
                    f"ADD COLUMN {_quote_identifier(column)} TEXT"
                )
                print(f"  ➕ Added column '{column}' to {table}")
        elif message == "Missing table":
            conn.execute(EXPECTED_SCHEMA[table])
            print(f"  🆕 Created new table: {table}")
    conn.commit()
    print("\n✅ Migration completed successfully.")
