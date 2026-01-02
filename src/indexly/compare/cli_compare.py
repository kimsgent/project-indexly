import sys
import json
from pathlib import Path

from .compare_engine import run_compare
from .render import render_result
from .models import FileCompareResult, FolderCompareResult

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def handle_compare(args):
    result, exit_code = run_compare(
        args.path_a,
        args.path_b,
        threshold=args.threshold,
        extensions=(
            set(getattr(args, "extensions", "").split(","))
            if getattr(args, "extensions", None)
            else None
        ),
        ignore=(
            set(getattr(args, "ignore", "").split(","))
            if getattr(args, "ignore", None)
            else None
        ),
    )

    if args.quiet:
        sys.exit(exit_code)

    if args.json:
        print(json.dumps(_result_to_dict(result), indent=2, default=str))
        sys.exit(exit_code)

    if args.summary_only:
        if isinstance(result, FolderCompareResult):
            _render_folder_summary(result, show_files=True)
        elif isinstance(result, FileCompareResult):
            _render_file_summary(result)
        sys.exit(exit_code)

    # Pass context to the renderer
    render_result(result, context=getattr(args, "context", 3))
    sys.exit(exit_code)


def _render_file_summary(result):
    """Display file comparison summary nicely using Rich."""
    mode_text = Text(result.tier.value.upper(), style="cyan")
    suffix_text = Text(result.path_a.suffix, style="magenta")
    status_text = Text()

    if result.identical:
        status_text.append("✔ IDENTICAL", style="green bold")
    elif result.similarity is not None:
        status_text.append(f"≈ SIMILAR ({result.similarity:.2f})", style="yellow bold")
    else:
        status_text.append("✖ MODIFIED", style="red bold")

    table = Table.grid(expand=True)
    table.add_column(justify="right")
    table.add_column(justify="left")

    table.add_row("File A:", str(result.path_a))
    table.add_row("File B:", str(result.path_b))
    table.add_row("Mode:", mode_text + Text(" (") + suffix_text + Text(")"))
    table.add_row("Status:", status_text)

    console.print(Panel(table, title="File Comparison Summary", border_style="blue"))


def _render_folder_summary(result, show_files: bool = False):
    """Display folder summary nicely using Rich."""
    s = result.summary
    table = Table(title="Folder Comparison Summary", border_style="blue", expand=True)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Count", style="magenta", justify="right")

    table.add_row("Identical", str(s.identical))
    table.add_row("Similar", str(s.similar))
    table.add_row("Modified", str(s.modified))
    table.add_row("Missing A", str(s.missing_a))
    table.add_row("Missing B", str(s.missing_b))

    console.print(table)

    if show_files and getattr(result, "files", None):
        file_table = Table(title="Files Details", border_style="green", expand=True)
        file_table.add_column("File", style="cyan")
        file_table.add_column("Status", style="magenta")

        for f in result.files:
            if f.identical:
                status = "[green]✔ IDENTICAL[/green]"
            elif getattr(f, "similarity", None) is not None:
                status = f"[yellow]≈ SIMILAR ({f.similarity:.2f})[/yellow]"
            else:
                status = "[red]✖ MODIFIED[/red]"
            file_table.add_row(str(f.path_a), status)

        console.print(file_table)


def _result_to_dict(result):
    if isinstance(result, FileCompareResult):
        return {
            "type": "file",
            "path_a": str(result.path_a),
            "path_b": str(result.path_b),
            "tier": result.tier.value,
            "identical": result.identical,
            "similarity": result.similarity,
            "diffs": [{"sign": d.sign, "text": d.text} for d in result.diffs],
        }

    return {
        "type": "folder",
        "path_a": str(result.path_a),
        "path_b": str(result.path_b),
        "summary": vars(result.summary),
        "files": [
            {
                "path_a": str(f.path_a),
                "path_b": str(f.path_b),
                "tier": f.tier.value,
                "identical": f.identical,
                "similarity": f.similarity,
            }
            for f in result.files
        ],
    }
