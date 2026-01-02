from pathlib import Path
from typing import Union
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text

from .models import FileCompareResult, FolderCompareResult
from .constants import CompareTier

console = Console()

CHECK = "✔"
SIMILAR = "≈"
MODIFIED = "✖"
MISSING_A = "+"
MISSING_B = "−"


def render_result(result: Union[FileCompareResult, FolderCompareResult], context: int = 3):
    if isinstance(result, FileCompareResult):
        _render_file_result(result, context=context)
    else:
        _render_folder_result(result)



def _render_file_result(result: FileCompareResult, context: int = 3) -> None:
    """Render file diff with GitHub-style colors and foldable skipped lines."""
    mode = result.tier.value.upper() if result.tier else "UNKNOWN"
    header = (
        f"[bold]File Comparison[/bold]\n"
        f"📁 A: {result.path_a}\n"
        f"📁 B: {result.path_b}\n"
        f"📝 Mode: {mode} ({result.path_a.suffix})"
    )
    console.print(Panel(header, expand=False, border_style="cyan"))

    if result.identical:
        console.print(f"[green]{CHECK} IDENTICAL[/green]")
        return

    status_text = f"{MODIFIED} MODIFIED"
    if result.similarity is not None:
        status_text += f" | Similarity: {result.similarity:.2f}"
    console.print(f"[yellow]{status_text}[/yellow]\n")

    if not result.diffs:
        return

    # Build structured diff lines
    lines = []
    for d in result.diffs:
        sign = getattr(d, "sign", " ")
        text = getattr(d, "text", "")
        if sign == "-":
            lines.append(("[red]-[/red]", text))
        elif sign == "+":
            lines.append(("[green]+[/green]", text))
        else:
            lines.append(("[dim] [/dim]", text))

    # Apply context folding
    displayed = []
    buffer = []

    def flush_buffer(buf):
        if len(buf) <= context * 2:
            for b_sign, b_text in buf:
                displayed.append(f"{b_sign} {b_text}")
        else:
            for b_sign, b_text in buf[:context]:
                displayed.append(f"{b_sign} {b_text}")
            displayed.append(f"[dim]… {len(buf) - context*2} lines hidden[/dim]")
            for b_sign, b_text in buf[-context:]:
                displayed.append(f"{b_sign} {b_text}")

    for sign, text in lines:
        if sign in ("[red]-[/red]", "[green]+[/green]"):
            if buffer:
                flush_buffer(buffer)
                buffer = []
            displayed.append(f"{sign} {text}")
        else:
            buffer.append((sign, text))

    if buffer:
        flush_buffer(buffer)

    # Print final diff
    for line in displayed:
        console.print(line)


def _render_folder_result(result: FolderCompareResult) -> None:
    s = getattr(result, "summary", None)
    if not s:
        console.print("[red]No summary available.[/red]")
        return

    header = (
        f"[bold]Folder Comparison[/bold]\n📁 A: {result.path_a}\n📁 B: {result.path_b}"
    )
    console.print(Panel(header, expand=False, border_style="cyan"))

    table = Table(title="Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_row("Identical", str(s.identical))
    table.add_row("Similar", str(s.similar))
    table.add_row("Modified", str(s.modified))
    table.add_row("Missing A", str(s.missing_a))
    table.add_row("Missing B", str(s.missing_b))
    console.print(table)

    if getattr(result, "files", None):
        table_files = Table(
            title="Files Detail", show_header=True, header_style="bold magenta"
        )
        table_files.add_column("File")
        table_files.add_column("Status")
        for f in result.files:
            if f.identical:
                symbol = f"[green]{CHECK}[/green]"
                status = "identical"
            elif getattr(f, "similarity", None) is not None:
                symbol = f"[yellow]{SIMILAR}[/yellow]"
                status = f"similar ({f.similarity:.2f})"
            else:
                symbol = f"[red]{MODIFIED}[/red]"
                status = "modified"
            rel = getattr(f.path_a, "name", "unknown")
            table_files.add_row(rel, f"{symbol} {status}")
        console.print(table_files)
