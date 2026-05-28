import pandas as pd
from indexly.datasets.resolver import resolve_dataset


def load_dataframe(
    file_name: str, use_cleaned: bool = True, use_raw: bool = False
) -> pd.DataFrame:
    resolved = resolve_dataset(file_name, use_cleaned=use_cleaned, use_raw=use_raw)
    return pd.DataFrame(resolved.df)
