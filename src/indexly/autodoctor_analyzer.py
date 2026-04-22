from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from .analysis_result import AnalysisResult
from .analyze_utils import save_analysis_result
from .autodoctor_db_pipeline import analyze_autodoctor_db_file
from .autodoctor_detect import detect_autodoctor_json
from .autodoctor_json_pipeline import analyze_autodoctor_json_file
from .universal_loader import _safe_read_json_text, detect_and_load

console = Console()


def analyze_autodoctor(args: Any) -> AnalysisResult | None:
    path = Path(
        getattr(args, "path", None)
        or getattr(args, "file", None)
        or getattr(args, "db_path", None)
        or ""
    ).resolve()
    if not path.exists():
        console.print(f"[red]❌ File not found: {path}[/red]")
        return None

    source_mode = getattr(args, "source", "auto")

    if source_mode in {"auto", "json"} and path.suffix.lower() in {".json", ".ndjson", ".gz"}:
        try:
            raw_text = _safe_read_json_text(path)
            raw = json.loads(raw_text) if raw_text else None
        except Exception:
            raw = None
        if source_mode == "json" or detect_autodoctor_json(raw):
            df, summary, _ = analyze_autodoctor_json_file(path, raw=raw, args=args, verbose=True)
            metadata = {
                "analysis_profile": "autodoctor",
                "autodoctor_kind": "json",
                "source_type": "json",
            }
            if not getattr(args, "no_persist", False):
                save_analysis_result(
                    file_path=path,
                    file_type="autodoctor-json",
                    summary=summary,
                    sample_data=df,
                    metadata=metadata,
                    row_count=len(df) if df is not None else 0,
                    col_count=len(df.columns) if df is not None else 0,
                )
            return AnalysisResult(
                file_path=str(path),
                file_type="autodoctor-json",
                df=df,
                summary=summary,
                metadata=metadata,
                cleaned=True,
                persisted=not getattr(args, "no_persist", False),
            )

    load_result = detect_and_load(path, args)
    metadata = (load_result or {}).get("metadata", {}) or {}
    if source_mode in {"auto", "db"} and metadata.get("analysis_profile") == "autodoctor":
        df, summary, _ = analyze_autodoctor_db_file(path, args=args, verbose=True)
        if not getattr(args, "no_persist", False):
            save_analysis_result(
                file_path=path,
                file_type="autodoctor-db",
                summary=summary,
                sample_data=df,
                metadata=metadata,
                row_count=len(df) if df is not None else 0,
                col_count=len(df.columns) if df is not None else 0,
            )
        return AnalysisResult(
            file_path=str(path),
            file_type="autodoctor-db",
            df=df,
            summary=summary,
            metadata=metadata,
            cleaned=True,
            persisted=not getattr(args, "no_persist", False),
        )

    console.print(
        "[yellow]⚠️ Input was not recognized as an AutoDoctor report or database.[/yellow]"
    )
    console.print(
        "[dim]Try `analyze-json`, `analyze-db`, or `analyze-file` for generic handling.[/dim]"
    )
    return None
