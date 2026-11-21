"""Regression coverage for the agent-facing documentation navigation graph."""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_documentation_graph import validate_graph  # noqa: E402


def test_tracked_documentation_graph_is_valid():
    validate_graph(ROOT / "documentation-graph.yaml")


def test_documentation_graph_rejects_duplicate_yaml_keys(tmp_path):
    graph = tmp_path / "duplicate.yaml"
    contents = "schema_version: 1\nschema_version: 1\n"
    graph.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate key"):
        validate_graph(graph)


@pytest.mark.parametrize(
    "field", ["source_paths", "test_paths", "documentation_targets"]
)
def test_documentation_graph_requires_complete_area_routing(tmp_path, field):
    graph = yaml.safe_load(
        (ROOT / "documentation-graph.yaml").read_text(encoding="utf-8")
    )
    graph["nodes"]["IDX-01"][field] = []
    candidate = tmp_path / "missing-routing.yaml"
    candidate.write_text(yaml.safe_dump(graph), encoding="utf-8")
    expected_message = rf"node IDX-01\.{field} must not be empty"

    with pytest.raises(ValueError, match=expected_message):
        validate_graph(candidate)
