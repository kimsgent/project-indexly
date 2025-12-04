# profiler_utils.py

from typing import Dict, Any
import pandas as pd

# ---------------------------------------
# Numeric statistics
# ---------------------------------------
def numeric_stats(df: pd.DataFrame, percentiles=[0.25, 0.5, 0.75]) -> Dict[str, Any]:
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        return {}

    out = {}
    base = numeric.agg(['count', 'mean', 'std', 'min', 'max'])
    q = numeric.quantile(percentiles)

    for col in numeric.columns:
        out[col] = {
            "count": base.loc["count", col],
            "mean": base.loc["mean", col],
            "std": base.loc["std", col],
            "min": base.loc["min", col],
            "25%": q.loc[0.25, col],
            "50%": q.loc[0.5, col],
            "75%": q.loc[0.75, col],
            "IQR": q.loc[0.75, col] - q.loc[0.25, col],
            "max": base.loc["max", col],
            "is_numeric": True,
        }

        # NaN → None
        for k, v in out[col].items():
            out[col][k] = None if pd.isna(v) else v

    return out


# ---------------------------------------
# Non-numeric summary
# ---------------------------------------
def non_numeric_summary(df: pd.DataFrame) -> Dict[str, Any]:
    out = {}
    for col in df.select_dtypes(exclude="number").columns:
        ser = df[col].dropna().astype(str)
        try:
            vc = ser.value_counts()
            out[col] = {
                "unique": int(ser.nunique()),
                "nulls": int(df[col].isna().sum()),
                "sample": ser.head(3).tolist(),
                "top": vc.head(10).to_dict(),
            }
        except Exception:
            out[col] = {"unique": None, "nulls": None, "sample": [], "top": {}}
    return out


# ---------------------------------------
# Null ratios
# ---------------------------------------
def null_ratios(df: pd.DataFrame) -> Dict[str, Any]:
    total = len(df)
    out = {}
    for col in df.columns:
        n = int(df[col].isna().sum())
        out[col] = {
            "nulls": n,
            "null_pct": round((n / total) * 100, 2) if total > 0 else None,
        }
    return out


# ---------------------------------------
# Duplicate detection
# ---------------------------------------
def duplicate_stats(df: pd.DataFrame) -> Dict[str, int]:
    out = {}
    for col in df.columns:
        try:
            out[col] = int(df[col].duplicated().sum())
        except Exception:
            out[col] = None
    return out


def duplicate_rows(df: pd.DataFrame) -> int:
    return int(df.duplicated().sum())


# ---------------------------------------
# Key inference
# ---------------------------------------
def infer_key_candidates(df: pd.DataFrame) -> Dict[str, Any]:
    total = len(df)
    out = {}

    for col in df.columns:
        ser = df[col]
        nulls = ser.isna().sum()
        dupes = ser.duplicated().sum()

        if nulls == 0 and dupes == 0:
            out[col] = "unique_key"
        elif nulls == 0 and dupes < (0.01 * total):
            out[col] = "likely_key"
        else:
            out[col] = None

    return out


## ---------------------------------------
# Full unified profile builder
# ---------------------------------------
def profile_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
    core = {
        "row_count": len(df),
        "columns": list(df.columns),
        "numeric_summary": numeric_stats(df),
        "null_ratios": null_ratios(df),
        "duplicate_columns": duplicate_stats(df),
        "duplicate_rows": duplicate_rows(df),
        "key_candidates": infer_key_candidates(df),
    }

    # everything non-core → extra
    extra = {
        "non_numeric_summary": non_numeric_summary(df)
    }

    core["extra"] = extra
    return core

