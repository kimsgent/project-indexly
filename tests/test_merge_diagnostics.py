import pandas as pd
import pytest

from indexly.inference.merge_engine import merge_dataframes


def test_one_to_many_merge_reports_cardinality_without_aggregation():
    left = pd.DataFrame({"id": [1, 2], "group": ["A", "B"]})
    right = pd.DataFrame({"id": [1, 1, 2], "value": [10, 11, 20]})

    merged, metadata = merge_dataframes([left, right], merge_on="id", agg="none")

    assert len(merged) == 3
    assert metadata["join_cardinality"] == "one-to-many"
    assert metadata["duplicate_keys_detected"] == [False, True]


def test_many_to_many_merge_fails_without_explicit_aggregation():
    left = pd.DataFrame({"id": [1, 1], "group": ["A", "B"]})
    right = pd.DataFrame({"id": [1, 1], "value": [10, 11]})

    with pytest.raises(ValueError, match="Many-to-many merge detected"):
        merge_dataframes([left, right], merge_on="id", agg="none")


def test_merge_supports_multiple_keys_and_reports_join_keys():
    left = pd.DataFrame({"id": [1, 1], "day": [1, 2], "group": ["A", "B"]})
    right = pd.DataFrame({"id": [1, 1], "day": [1, 2], "value": [10, 20]})

    merged, metadata = merge_dataframes([left, right], merge_on=["id", "day"])

    assert len(merged) == 2
    assert metadata["join_keys"] == ["id", "day"]
    assert metadata["join_cardinality"] == "one-to-one"
