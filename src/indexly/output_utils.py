# output_utils.py
import re
from rich import print as rprint
from .utils import highlight_term
from .db_utils import get_tags_for_file

# printing search results

def print_search_results(results, term, context_chars=150):
    rprint(f"[bold green]Found {len(results)} matches:[/bold green]")
    for row in results:
        rprint(f"[bold cyan]{row['path']}[/bold cyan]")

        tags = get_tags_for_file(row["path"])
        if tags:
            rprint(f"[dim white][Tags: {', '.join(tags)}][/dim white]")

        # Snippet already prebuilt in search_fts5 / search_regex
        snippet = row.get("snippet", "") or row.get("content", "")

        highlighted = snippet
        for word in re.findall(r"\w+", term):
            highlighted = highlight_term(highlighted, word)

        rprint(f"[yellow]{highlighted}[/yellow]\n")

        
# printing regex results

def print_regex_results(results, pattern, context_chars):
    for row in results:
        # ✅ Path
        rprint(f"[bold cyan]{row['path']}[/bold cyan]")

        # ✅ Tags (same as FTS5)
        tags = get_tags_for_file(row["path"])
        if tags:
            rprint(f"[dim][Tags: {', '.join(tags)}][/dim]")

        # ✅ Snippet building & highlighting
        text = row.get("content") or row.get("snippet") or ""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            snippet = text[
                max(0, match.start() - context_chars): match.end() + context_chars
            ]
            highlighted_snippet = snippet.replace(
                match.group(0), f"[yellow bold]{match.group(0)}[/yellow bold]"
            )
            rprint(f"{highlighted_snippet}\n")
        else:
            rprint("[dim]No preview available[/dim]\n")
