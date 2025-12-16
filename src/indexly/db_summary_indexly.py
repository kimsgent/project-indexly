# src/indexly/db_summary_indexly.py
import re
import pandas as pd
import sqlite3
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


class IndexlySummaryBuilder:
    def __init__(self, db_path, raw):
        self.db_path = Path(db_path)
        self.raw = raw or {}

    def build(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        summary = {}

        summary["core"] = self._core_stats(cur)
        summary["metadata_completeness"] = self._metadata_completeness(cur)
        summary["tags"] = self._tag_stats(cur)
        timeline, df_meta = self._timeline_info(cur)
        summary["timeline"] = timeline
        summary["tables"] = self._table_counts(cur)
        summary["fts_integrity"] = self._fts_integrity(cur)

        if not df_meta.empty and "path" in df_meta.columns:
            summary["non_numeric"] = self._analyze_paths(df_meta)

        self._print_console(summary)
        conn.close()
        return summary

    # ------------------------------------
    # Core
    # ------------------------------------
    def _core_stats(self, cur):
        total_files = self._count(cur, "file_index")
        total_meta = self._count(cur, "file_metadata")
        total_vocab = self._count(cur, "file_index_vocab")

        return {
            "total_rows_file_index": total_files,
            "total_rows_metadata": total_meta,
            "vocab_entries": total_vocab,
            "db_size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 2),
        }

    # ------------------------------------
    # Metadata completeness
    # ------------------------------------
    def _metadata_completeness(self, cur):
        try:
            df = pd.read_sql_query("SELECT * FROM file_metadata", cur.connection)
        except Exception:
            return {}

        fields = ["title", "author", "created", "last_modified", "mime_type"]

        return {
            f: round(100 * df[f].isna().mean(), 1) if f in df else 100.0 for f in fields
        }

    # ------------------------------------
    # Tag stats
    # ------------------------------------
    def _tag_stats(self, cur):
        try:
            df = pd.read_sql_query("SELECT tags FROM file_tags", cur.connection)
            if df.empty:
                return {}
            return (
                df["tags"]
                .dropna()
                .str.split(",", expand=True)
                .stack()
                .str.strip()
                .value_counts()
                .head(20)
                .to_dict()
            )
        except Exception:
            return {}

    # ------------------------------------
    # Timeline
    # ------------------------------------
    def _timeline_info(self, cur):
        try:
            df = pd.read_sql_query(
                "SELECT path, created, last_modified FROM file_metadata",
                cur.connection,
            )
            df["created"] = pd.to_datetime(df["created"], errors="coerce")
            df["last_modified"] = pd.to_datetime(df["last_modified"], errors="coerce")

            return {
                "oldest_created": df["created"].min(),
                "newest_modified": df["last_modified"].max(),
            }, df
        except Exception:
            return {}, pd.DataFrame()

    # ------------------------------------
    # Table counts
    # ------------------------------------
    def _table_counts(self, cur):
        return {tbl: self._count(cur, tbl) for tbl in self.raw.get("tables", [])}

    # ------------------------------------
    # FTS integrity
    # ------------------------------------
    def _fts_integrity(self, cur):
        try:
            fi_count = self._count(cur, "file_index")
            return {
                "file_index_count": fi_count,
                "file_index_content_count": self._count(cur, "file_index_content"),
                "file_index_vocab_count": self._count(cur, "file_index_vocab"),
                "file_index_docsize_count": self._count(cur, "file_index_docsize"),
                "mismatches": any(
                    [
                        fi_count != self._count(cur, "file_index_content"),
                        fi_count != self._count(cur, "file_index_docsize"),
                    ]
                ),
            }
        except Exception:
            return {"mismatches": True}

    # ------------------------------------
    # Path analysis
    # ------------------------------------
    def _analyze_paths(self, df):
        pattern = re.compile(
            r".*\\(?P<year>\d{4})\\(?P<month>\d{1,2})\\(?P<customer>[^\\]+)\\(?P<ticket>[^\\]+)\.(?P<ext>\w+)$",
            re.IGNORECASE,
        )

        records = []
        for p in df["path"].dropna():
            m = pattern.match(p.replace("/", "\\"))
            if m:
                records.append(m.groupdict())
            else:
                parts = Path(p).parts
                records.append(
                    {
                        "year": parts[-4] if len(parts) >= 4 else None,
                        "month": parts[-3] if len(parts) >= 3 else None,
                        "customer": parts[-2] if len(parts) >= 2 else None,
                        "ticket": Path(p).stem,
                        "ext": Path(p).suffix.lstrip("."),
                    }
                )

        pdf = pd.DataFrame(records)
        summary = {
            col: {
                "top": pdf[col].value_counts(dropna=True).head(10).to_dict(),
                "total": pdf[col].count(),
            }
            for col in ["customer", "year", "month", "ticket", "ext"]
        }

        if "last_modified" in df.columns:
            df["last_modified"] = pd.to_datetime(df["last_modified"], errors="coerce")
            summary["last_modified"] = {
                "earliest": df["last_modified"].min(),
                "latest": df["last_modified"].max(),
                "by_month": df["last_modified"]
                .dt.to_period("M")
                .value_counts()
                .sort_index()
                .to_dict(),
            }

        return summary

    # ------------------------------------
    # Utils
    # ------------------------------------
    def _count(self, cur, table):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0]
        except Exception:
            return None

    # ------------------------------------
    # Console rendering
    # ------------------------------------
    def _print_console(self, summary):

      tbl = Table(
          title="[bold cyan]Indexly DB Summary[/]",
          show_lines=True,
          title_style="bold cyan"
      )
      tbl.add_column("[bold yellow]Metric[/]")
      tbl.add_column("[bold yellow]Value[/]")

      for k, v in summary["core"].items():
          tbl.add_row(k, str(v))
      console.print(tbl)

      # ------------------------------------
      # Metadata Completeness
      # ------------------------------------
      meta_tbl = Table(
          title="[bold cyan]Metadata Completeness (%)",
          title_style="bold cyan"
      )
      meta_tbl.add_column("[bold yellow]Field[/]")
      meta_tbl.add_column("[bold yellow]Missing %[/]")

      for k, v in summary["metadata_completeness"].items():
          meta_tbl.add_row(k, str(v))
      console.print(meta_tbl)

      # ------------------------------------
      # Tags
      # ------------------------------------
      tag_tbl = Table(
          title="[bold cyan]Top 20 Tags",
          title_style="bold cyan"
      )
      tag_tbl.add_column("[bold yellow]Tag[/]")
      tag_tbl.add_column("[bold yellow]Count[/]")

      for k, v in summary["tags"].items():
          tag_tbl.add_row(k, str(v))
      console.print(tag_tbl)

      # ------------------------------------
      # FTS5 Integrity
      # ------------------------------------
      fts_tbl = Table(
          title="[bold cyan]FTS5 Integrity",
          title_style="bold cyan"
      )
      fts_tbl.add_column("[bold yellow]Check[/]")
      fts_tbl.add_column("[bold yellow]Result[/]")

      for k, v in summary["fts_integrity"].items():
          fts_tbl.add_row(k, str(v))
      console.print(fts_tbl)

      # ------------------------------------
      # Unified / Text fallback for non-numeric sections
      # ------------------------------------
      non_numeric = summary.get("non_numeric", {})
      col_names = list(non_numeric.keys())

      # Unified table if manageable
      if 1 <= len(col_names) <= 6:
          unified = Table(
              title="[bold magenta]Non-Numeric Columns Overview[/]",
              show_lines=True,
              title_style="bold magenta"
          )
          unified.add_column("[bold yellow]Column[/]")
          unified.add_column("[bold yellow]Unique[/]")
          unified.add_column("[bold yellow]Nulls[/]")
          unified.add_column("[bold yellow]Sample[/]")
          unified.add_column("[bold yellow]Top-1[/]")
          unified.add_column("[bold yellow]Top-1 Count[/]")
          unified.add_column("[bold yellow]Top-2[/]")
          unified.add_column("[bold yellow]Top-2 Count[/]")
          unified.add_column("[bold yellow]Top-3[/]")
          unified.add_column("[bold yellow]Top-3 Count[/]")

          for col, info in non_numeric.items():
              top_items = list(info.get("top", {}).items())[:3]
              t1, c1 = top_items[0] if len(top_items) > 0 else ("", "")
              t2, c2 = top_items[1] if len(top_items) > 1 else ("", "")
              t3, c3 = top_items[2] if len(top_items) > 2 else ("", "")
              sample = ", ".join(map(str, info.get("sample", [])[:3]))

              unified.add_row(
                  col,
                  str(info.get("unique")),
                  str(info.get("nulls")),
                  sample,
                  str(t1), str(c1),
                  str(t2), str(c2),
                  str(t3), str(c3),
              )

          console.print(unified)

      # Text fallback for large / complex datasets
      else:
          console.print("\n[bold magenta]Non-Numeric Column Overview[/bold magenta]\n")
          for col, info in non_numeric.items():
              sample = ", ".join(map(str, info.get("sample", [])[:3]))
              console.print(
                  f"- {col}: {info.get('unique')} unique, "
                  f"nulls={info.get('nulls')}, "
                  f"sample=[{sample}], "
                  f"top={info.get('top', {})}"
              )

