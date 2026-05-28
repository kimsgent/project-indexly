from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from rich.console import Console
from rich.table import Table

from indexly.datasets.resolver import resolve_dataset
from indexly.datasets.schema import ResolvedDataset

from .merge_engine import merge_dataframes

console = Console()


@dataclass(frozen=True)
class RoutedInferenceDataset:
    df: pd.DataFrame
    datasets: list[ResolvedDataset]
    merge_metadata: dict | None
    selected_columns: list[str]


def route_inference_datasets(args) -> RoutedInferenceDataset:
    use_cleaned = not getattr(args, "use_raw", False)
    merge_keys = _merge_keys(getattr(args, "merge_on", None))
    selected_columns = _selected_columns(args, merge_keys)
    files = getattr(args, "files", [])
    required_columns = selected_columns if len(files) == 1 else merge_keys

    resolved = [
        resolve_dataset(
            identifier,
            use_cleaned=use_cleaned,
            use_raw=getattr(args, "use_raw", False),
            columns=selected_columns,
            required_columns=required_columns,
            ignore_hash=getattr(args, "ignore_hash", False),
        )
        for identifier in files
    ]

    if len(resolved) == 1:
        _print_single_dataset_diagnostics(resolved[0], selected_columns)
        return RoutedInferenceDataset(
            df=resolved[0].df,
            datasets=resolved,
            merge_metadata=None,
            selected_columns=selected_columns,
        )

    if not merge_keys:
        raise ValueError("--merge-on is required when multiple files are provided.")

    merged, merge_metadata = merge_dataframes(
        dfs=[dataset.df for dataset in resolved],
        merge_on=merge_keys,
        how=getattr(args, "merge_how", "inner"),
        agg=getattr(args, "agg", "none"),
    )
    _print_merge_diagnostics(resolved, merge_metadata, selected_columns)
    return RoutedInferenceDataset(
        df=merged,
        datasets=resolved,
        merge_metadata=merge_metadata,
        selected_columns=selected_columns,
    )


def _selected_columns(args, merge_keys: list[str]) -> list[str]:
    columns: list[str] = list(merge_keys)
    if getattr(args, "y", None):
        columns.append(args.y)
    if getattr(args, "x", None):
        columns.extend(args.x)
    if getattr(args, "group", None):
        columns.append(args.group)
    if getattr(args, "interaction", None):
        columns.extend(args.interaction)
    return list(dict.fromkeys(column for column in columns if column))


def _merge_keys(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _print_single_dataset_diagnostics(
    dataset: ResolvedDataset, selected_columns: list[str]
) -> None:
    table = Table(title="Inference Dataset", show_header=True, header_style="bold cyan")
    table.add_column("Input")
    table.add_column("Resolved via")
    table.add_column("Rows")
    table.add_column("Columns")
    table.add_row(
        dataset.identifier,
        dataset.resolution,
        str(dataset.row_count),
        str(dataset.col_count),
    )
    console.print(table)
    _print_dataset_warnings([dataset])
    if selected_columns:
        console.print(
            f"[dim]Columns selected for inference: {', '.join(selected_columns)}[/dim]"
        )


def _print_merge_diagnostics(
    datasets: list[ResolvedDataset],
    metadata: dict,
    selected_columns: list[str],
) -> None:
    table = Table(title="Merge Diagnostics", show_header=True, header_style="bold cyan")
    table.add_column("Input")
    table.add_column("Resolved via")
    table.add_column("Rows")
    table.add_column("Duplicate keys")

    duplicate_flags = metadata.get("duplicate_keys_detected", [])
    for index, dataset in enumerate(datasets):
        table.add_row(
            dataset.identifier,
            dataset.resolution,
            str(metadata.get("original_row_counts", [dataset.row_count])[index]),
            "yes" if duplicate_flags[index] else "no",
        )
    console.print(table)
    _print_dataset_warnings(datasets)
    console.print(f"[dim]Join keys: {', '.join(metadata.get('join_keys', []))}[/dim]")
    console.print(
        f"[dim]Join type: {metadata.get('join_cardinality', 'unknown')}[/dim]"
    )
    console.print(f"[dim]Merged rows: {metadata.get('merged_row_count', 0)}[/dim]")
    console.print(
        f"[dim]Aggregation mode: {metadata.get('aggregation_mode', 'none')}[/dim]"
    )
    if selected_columns:
        console.print(
            f"[dim]Columns selected for inference: {', '.join(selected_columns)}[/dim]"
        )


def _print_dataset_warnings(datasets: list[ResolvedDataset]) -> None:
    for dataset in datasets:
        for warning in dataset.warnings:
            console.print(f"[yellow]Warning:[/] {warning}")
