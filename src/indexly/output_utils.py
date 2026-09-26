# output_utils.py
"""Human-readable search result rendering helpers."""

import re
import sys
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from rich.console import Console
from rich.text import Text

from .db_utils import get_tags_for_file

DEFAULT_PAGE_SIZE = 10


def _stream_is_tty(stream: TextIO) -> bool:
    """Return whether *stream* is safely usable for interactive paging."""
    try:
        isatty = getattr(stream, "isatty")
        return callable(isatty) and bool(isatty())
    except (AttributeError, OSError, ValueError):
        return False


def _read_navigation(input_stream: TextIO, console: Console) -> str | None:
    """Read one pager instruction, returning ``None`` for a clean stop."""
    while True:
        console.print(
            "[dim]Enter: next · Space: show remaining · q: quit[/dim]", end=" "
        )
        try:
            response = input_stream.readline()
        except (AttributeError, EOFError, KeyboardInterrupt, OSError, ValueError):
            return None

        if response == "":
            return None

        response = response.rstrip("\r\n")
        if response == "":
            return "next"
        if response == " ":
            return "remaining"
        if response.casefold() == "q":
            return "quit"

        console.print("[dim]Use Enter, Space, or q.[/dim]")


def _render_paginated_results(
    results: Sequence[dict[str, Any]],
    render_item: Callable[[dict[str, Any], Console], None],
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> None:
    """Render an already-computed result sequence, paging only interactive output."""
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    console = Console(file=output_stream)
    result_count = len(results)

    if not result_count:
        return

    interactive = _stream_is_tty(input_stream) and _stream_is_tty(output_stream)
    if not interactive or result_count <= page_size:
        console.print(f"[bold green]Found {result_count} matches:[/bold green]")
        for row in results:
            render_item(row, console)
        return

    total_pages = (result_count + page_size - 1) // page_size
    page_number = 1

    while True:
        first_result = (page_number - 1) * page_size
        last_result = min(first_result + page_size, result_count)
        console.print(
            "[bold green]"
            f"Found {result_count} matches — Page {page_number} of {total_pages} "
            f"(results {first_result + 1}–{last_result} of {result_count}):"
            "[/bold green]"
        )
        for row in results[first_result:last_result]:
            render_item(row, console)

        if last_result == result_count:
            return

        navigation = _read_navigation(input_stream, console)
        if navigation in {None, "quit"}:
            return
        if navigation == "remaining":
            for row in results[last_result:]:
                render_item(row, console)
            return

        page_number += 1


def print_search_results(
    results: Sequence[dict[str, Any]],
    term: str,
    context_chars: int = 150,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> None:
    """Render FTS search results while preserving the supplied result order."""

    def render_item(row: dict[str, Any], console: Console) -> None:
        console.print(f"[bold cyan]{row['path']}[/bold cyan]")

        tags = get_tags_for_file(row["path"])
        if tags:
            console.print(f"[dim white][Tags: {', '.join(tags)}][/dim white]")

        snippet = row.get("snippet", "") or row.get("content", "")
        highlighted = Text(snippet, style="yellow")
        for word in re.findall(r"\w+", term):
            pattern = re.compile(rf"({re.escape(word)})", re.IGNORECASE)
            for match in pattern.finditer(snippet):
                highlighted.stylize("bold red", *match.span())

        console.print(highlighted)

    _render_paginated_results(
        results,
        render_item,
        input_stream=input_stream,
        output_stream=output_stream,
        page_size=page_size,
    )


def print_regex_results(
    results: Sequence[dict[str, Any]],
    pattern: str,
    context_chars: int,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> None:
    """Render regex results while preserving the supplied result order."""

    def render_item(row: dict[str, Any], console: Console) -> None:
        console.print(f"[bold cyan]{row['path']}[/bold cyan]")

        tags = get_tags_for_file(row["path"])
        if tags:
            console.print(f"[dim][Tags: {', '.join(tags)}][/dim]")

        text = row.get("content") or row.get("snippet") or ""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            snippet = text[
                max(0, match.start() - context_chars) : match.end() + context_chars
            ]
            highlighted_snippet = snippet.replace(
                match.group(0), f"[yellow bold]{match.group(0)}[/yellow bold]"
            )
            console.print(f"{highlighted_snippet}\n")
        else:
            console.print("[dim]No preview available[/dim]\n")

    _render_paginated_results(
        results,
        render_item,
        input_stream=input_stream,
        output_stream=output_stream,
        page_size=page_size,
    )
