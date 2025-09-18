# output_utils.py
import re
from rich import print as rprint
from .utils import highlight_term
from .db_utils import get_tags_for_file

# printing search results

from rich.console import Console
from rich.text import Text

console = Console(force_terminal=True)

def print_search_results(results, term, context_chars=150):
    console.print(f"[bold green]Found {len(results)} matches:[/bold green]")

    for row in results:
        console.print(f"[bold cyan]{row['path']}[/bold cyan]")

        tags = get_tags_for_file(row["path"])
        if tags:
            console.print(f"[dim white][Tags: {', '.join(tags)}][/dim white]")

        snippet = row.get("snippet", "") or row.get("content", "")
        highlighted = Text(snippet, style="yellow")  # base yellow style

        # Highlight each search term in bold red
        for word in re.findall(r"\w+", term):
            pattern = re.compile(rf"({re.escape(word)})", re.IGNORECASE)
            for match in pattern.finditer(snippet):
                start, end = match.span()
                highlighted.stylize("bold red", start, end)

        console.print(highlighted)

        
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
