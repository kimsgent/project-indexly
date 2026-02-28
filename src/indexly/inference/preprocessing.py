import pandas as pd


def select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Select a subset of columns from a DataFrame with validation.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame.
    columns : list[str]
        List of column names to extract.

    Returns
    -------
    pd.DataFrame
        A copy of the DataFrame containing only the requested columns.

    Raises
    ------
    ValueError
        If one or more requested columns are not present in the DataFrame.

    Notes
    -----
    - Performs strict validation to avoid silent failures.
    - Returns a copy to prevent unintended side effects on the original DataFrame.
    """
    # Identify columns that are missing from the DataFrame
    missing = [c for c in columns if c not in df.columns]

    # Fail fast if any requested column does not exist
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # Return a defensive copy of the selected columns
    return df[columns].copy()


def apply_na_policy(df: pd.DataFrame, policy: str = "drop") -> pd.DataFrame:
    """
    Apply a missing value (NA) handling policy to a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame.
    policy : str, default="drop"
        Strategy for handling missing values:
        - "drop"   : Remove rows containing any NA values.
        - "mean"   : Replace NA values with column-wise mean (numeric columns only).
        - "median" : Replace NA values with column-wise median (numeric columns only).

    Returns
    -------
    pd.DataFrame
        DataFrame after applying the specified NA policy.

    Raises
    ------
    ValueError
        If an unsupported policy is provided.

    Notes
    ------
    - Mean/median imputation only affects numeric columns.
    - Non-numeric columns remain unchanged during imputation.
    - The function does not modify the input DataFrame in-place.
    """
    # Drop all rows containing any missing values
    if policy == "drop":
        return df.dropna()

    # Impute missing numeric values with column means
    if policy == "mean":
        return df.fillna(df.mean(numeric_only=True))

    # Impute missing numeric values with column medians
    if policy == "median":
        return df.fillna(df.median(numeric_only=True))

    # Guard clause for unsupported policies
    raise ValueError("Invalid NA policy.")
