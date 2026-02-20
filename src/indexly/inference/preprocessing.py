import pandas as pd


def select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    return df[columns].copy()


def apply_na_policy(df: pd.DataFrame, policy: str = "drop") -> pd.DataFrame:
    if policy == "drop":
        return df.dropna()
    if policy == "mean":
        return df.fillna(df.mean(numeric_only=True))
    if policy == "median":
        return df.fillna(df.median(numeric_only=True))
    raise ValueError("Invalid NA policy.")

