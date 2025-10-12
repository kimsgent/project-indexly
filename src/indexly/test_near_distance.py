import re
import sqlite3
from rich.console import Console
from rich.table import Table
from indexly.search_core import search_fts5  # adjust import if needed
from indexly.config import DB_FILE

console = Console()

# Precompiled regex for NEAR normalization
_RE_NEAR = re.compile(r"\bNEAR\s*\(?\s*(\d+)?\s*\)?\b", re.IGNORECASE)

def has_near_distance_support() -> bool:
    """Check if the SQLite build supports NEAR/x syntax."""
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
        conn.execute("SELECT * FROM t WHERE c MATCH 'a NEAR/5 b'")
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False

_NEAR_X_SUPPORTED = has_near_distance_support()

def normalize_near_expr(expr: str, near_distance: int = 5) -> str:
    """Normalize NEAR() or NEAR constructs to NEAR/x or NEAR depending on support."""
    if not expr:
        return ""

    def _near_repl(match):
        n = match.group(1)
        return f"NEAR/{n or near_distance}"

    normalized = _RE_NEAR.sub(_near_repl, expr)

    if not _NEAR_X_SUPPORTED:
        # Downgrade to plain NEAR
        normalized = re.sub(r"NEAR/\d+", "NEAR", normalized, flags=re.IGNORECASE)

    return normalized.strip()


def run_test(query: str, near_distance: int, label: str):
    console.rule(label)
    normalized_query = normalize_near_expr(query, near_distance)

    console.print(f"[bold yellow]Normalized FTS expression:[/bold yellow] {normalized_query}")
    if not _NEAR_X_SUPPORTED and "NEAR/" in normalized_query:
        console.print("[red]⚠️ NEAR/x unsupported — downgraded to plain NEAR[/red]")

    try:
        results = search_fts5(
            term=normalized_query,
            query=normalized_query,
            db_path=DB_FILE,
            near_distance=near_distance,
        )
    except sqlite3.OperationalError as e:
        console.print(f"[red]OperationalError:[/red] {e}")
        results = []

    table = Table(title=f"Results for: {normalized_query}")
    table.add_column("Path", style="cyan")
    table.add_column("Snippet", style="white")

    if results:
        for r in results:
            table.add_row(r.get("path", ""), r.get("snippet", ""))
    else:
        table.add_row("❌ No results", "")

    console.print(table)
    console.print("\n")


def main():
    # Test 1: Far-apart words (should match only with loose distance)
    query1 = '"data" NEAR "analysis"'
    run_test(query1, near_distance=3, label="❌ Should NOT match (distance too small)")
    run_test(query1, near_distance=100, label="✅ Should match (looser distance)")

    # Test 2: Close words (should match even with small distance)
    query2 = '"data" NEAR "analysis"'
    run_test(query2, near_distance=3, label="✅ Should match (very close words)")
    run_test(query2, near_distance=100, label="✅ Should also match (looser distance)")

    # Test 3: Logical operators with NEAR
    query3 = '"apple" AND "orange" NEAR/5'
    run_test(query3, near_distance=5, label="Logical AND + NEAR test")
    query4 = '"fox" OR "dog" NEAR/2'
    run_test(query4, near_distance=2, label="Logical OR + NEAR test")
    query5 = 'NOT "lazy" NEAR "dog"'
    run_test(query5, near_distance=3, label="Logical NOT + NEAR test")


if __name__ == "__main__":
    main()
