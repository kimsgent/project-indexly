from rich.console import Console
from rich.table import Table
from .search_core import search_fts5  # your existing function
from .config import DB_FILE

# Path to your actual DB
DB_PATH = "fts_index.db"   # adjust if different

console = Console()


def run_test(query, near_distance, label):
    console.rule(label)

    results = search_fts5(
      term=query,       # the actual NEAR(...) query string
      query=query,      # still required since your function signature has it
      db_path=DB_PATH,
      near_distance=near_distance,
  )


    table = Table(title=f"Results for: {query} (NEAR/{near_distance})")
    table.add_column("Path")
    table.add_column("Snippet")

    if results:
        for r in results:
            table.add_row(r.get("path", ""), r.get("snippet", ""))
    else:
        table.add_row("❌ No results", "")

    console.print(table)
    console.print("\n")


def main():
    # Contradiction Test Case 1: Far apart words
    query1 = '"Mobile" NEAR "Inventur"'
    run_test(query1, near_distance=3,
             label="❌ Should NOT match (distance too small)")
    run_test(query1, near_distance=100,
             label="✅ Should match (loose distance)")

    # Control Test Case 2: Close words
    query2 = '"Kunde" NEAR "anlegen"'
    run_test(query2, near_distance=3,
             label="✅ Should match (very close words)")
    run_test(query2, near_distance=100,
             label="✅ Should also match (looser distance)")


if __name__ == "__main__":
    main()
