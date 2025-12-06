# profiler_utils.py

import pandas as pd
from typing import Dict, Any

# ---------------------------------------
# Sampling defaults
# ---------------------------------------
def determine_sample_size(total_rows: int, user_size: int | None) -> int | None:
    if user_size is not None:
        return user_size

    if total_rows < 200_000:
        return None

    if total_rows <= 2_000_000:
        return max(5_000, min(int(total_rows * 0.05), 100_000))

    return max(10_000, min(int(total_rows * 0.01), 100_000))


def sample_dataframe(df: pd.DataFrame, user_size: int | None) -> pd.DataFrame:
    total = len(df)
    n = determine_sample_size(total, user_size)

    if n is None or n >= total:
        print(f"ℹ️ Using full table ({total} rows)")
        return df

    print(f"ℹ️ Sampling {n} rows from {total} total rows")
    return df.sample(n=n, random_state=42)


# ---------------------------------------
# Numeric statistics (fast_mode aware)
# ---------------------------------------
def numeric_stats(df: pd.DataFrame, fast_mode: bool = False,
                  percentiles=[0.25, 0.5, 0.75]) -> Dict[str, Any]:
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        return {}

    # Fast mode: skip percentiles & std (expensive)
    if fast_mode:
        base = numeric.agg(['count', 'mean', 'min', 'max'])
        out = {}

        for col in numeric.columns:
            out[col] = {
                "count": base.loc["count", col],
                "mean": base.loc["mean", col],
                "min": base.loc["min", col],
                "max": base.loc["max", col],
                "std": None,
                "25%": None,
                "50%": None,
                "75%": None,
                "IQR": None,
                "is_numeric": True,
            }
        return out

    # Full stats
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

        for k, v in out[col].items():
            out[col][k] = None if pd.isna(v) else v

    return out


# ---------------------------------------
# Non-numeric summary (fast-mode light)
# ---------------------------------------
def non_numeric_summary(df: pd.DataFrame, fast_mode: bool = False) -> Dict[str, Any]:
    out = {}
    for col in df.select_dtypes(exclude="number").columns:
        try:
            ser = df[col].dropna().apply(
                lambda x: str(x) if not isinstance(x, bytes) else x.decode("utf-8", errors="ignore")
            )

            if fast_mode:
                out[col] = {
                    "unique": int(ser.nunique()),
                    "nulls": int(df[col].isna().sum()),
                    "sample": ser.head(3).tolist(),
                    "top": {},
                }
                continue

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
def duplicate_stats(df: pd.DataFrame, fast_mode: bool = False) -> Dict[str, int]:
    if fast_mode:
        # Light-weight check only
        return {col: None for col in df.columns}

    out = {}
    for col in df.columns:
        try:
            out[col] = int(df[col].duplicated().sum())
        except Exception:
            out[col] = None
    return out


def duplicate_rows(df: pd.DataFrame, fast_mode: bool = False) -> int:
    return 0 if fast_mode else int(df.duplicated().sum())


# ---------------------------------------
# Key inference
# ---------------------------------------
def infer_key_candidates(df: pd.DataFrame, fast_mode: bool = False) -> Dict[str, Any]:
    if fast_mode:
        return {}

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


# ---------------------------------------
# Full unified profile builder
# ---------------------------------------
def profile_dataframe(
    df: pd.DataFrame,
    sample_size: int | None = None,
    full_data: bool = False,
    fast_mode: bool = False
) -> Dict[str, Any]:

    if not full_data:
        df = sample_dataframe(df, sample_size)

    return {
        "row_count": len(df),
        "columns": list(df.columns),
        "numeric_summary": numeric_stats(df, fast_mode=fast_mode),
        "null_ratios": null_ratios(df),
        "duplicate_columns": duplicate_stats(df, fast_mode=fast_mode),
        "duplicate_rows": duplicate_rows(df, fast_mode=fast_mode),
        "key_candidates": infer_key_candidates(df, fast_mode=fast_mode),
        "extra": {
            "non_numeric_summary": non_numeric_summary(df, fast_mode=fast_mode)
        }
    }
