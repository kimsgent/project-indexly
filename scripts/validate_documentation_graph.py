#!/usr/bin/env python3
"""Validate the tracked agent-facing documentation navigation graph."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GRAPH = ROOT / "documentation-graph.yaml"
AREA_IDS = {f"IDX-{number:02d}" for number in range(1, 13)}
RISK_ID = re.compile(r"IDX-RISK-\d{3}$")
ROUTABLE_NODE_KINDS = {"area", "module"}


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that makes duplicate mapping keys an error."""


def _construct_mapping(
    loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False
):
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _fail(message: str) -> None:
    raise ValueError(message)


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be a mapping")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{label} must be a list")
    return value


def _validate_relative_path(root: Path, value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a non-empty repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        _fail(
            " is not a normalized repository-relative POSIX path: ".join(
                (label, repr(value))
            )
        )
    if not (root / path).exists():
        _fail(f"{label} does not exist: {value}")


def validate_graph(graph_path: Path, repository_root: Path = ROOT) -> None:
    """Validate structure, navigation references, and tracked paths."""
    try:
        graph = yaml.load(
            graph_path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader
        )
    except (OSError, yaml.YAMLError) as exc:
        _fail(f"cannot load {graph_path}: {exc}")

    graph = _require_mapping(graph, "graph")
    if graph.get("schema_version") != 1:
        _fail("schema_version must be 1")
    if graph.get("graph_id") != "indexly-documentation-navigation":
        _fail("graph_id must be indexly-documentation-navigation")

    vocabulary = _require_mapping(graph.get("vocabulary"), "vocabulary")
    node_kinds = set(
        _require_list(vocabulary.get("node_kinds"), "vocabulary.node_kinds")
    )
    relation_types = set(
        _require_list(
            vocabulary.get("relationship_types"),
            "vocabulary.relationship_types",
        )
    )
    if not node_kinds or not relation_types:
        _fail("vocabulary node kinds and relationship types must not be empty")

    nodes = _require_mapping(graph.get("nodes"), "nodes")
    if not AREA_IDS.issubset(nodes):
        missing_areas = sorted(AREA_IDS - set(nodes))
        _fail(f"nodes must define every area: missing {missing_areas}")

    for node_id, raw_node in nodes.items():
        node = _require_mapping(raw_node, f"node {node_id}")
        if node.get("kind") not in node_kinds:
            _fail(f"node {node_id} has unknown kind {node.get('kind')!r}")
        if not isinstance(node.get("title"), str) or not node["title"].strip():
            _fail(f"node {node_id} needs a non-empty title")
        if "path" in node:
            _validate_relative_path(
                repository_root, node["path"], f"node {node_id}.path"
            )
        for field in ("source_paths", "test_paths", "documentation_targets"):
            field_label = f"node {node_id}.{field}"
            if node["kind"] in ROUTABLE_NODE_KINDS:
                values = _require_list(node.get(field), field_label)
                if not values:
                    _fail(f"{field_label} must not be empty")
            elif field not in node:
                values = []
            else:
                values = _require_list(node[field], field_label)
            if field in {"source_paths", "test_paths"}:
                for index, path in enumerate(values):
                    path_label = f"{field_label}[{index}]"
                    _validate_relative_path(repository_root, path, path_label)
            else:
                for target in values:
                    target_node = nodes.get(target)
                    if (
                        not isinstance(target_node, dict)
                        or target_node.get("kind") != "documentation"
                    ):
                        message = "references unknown documentation target"
                        _fail(f"node {node_id} {message} {target!r}")
        for area_id in (
            _require_list(node["area_ids"], f"node {node_id}.area_ids")
            if "area_ids" in node
            else []
        ):
            if area_id not in AREA_IDS:
                _fail(f"node {node_id} has unknown area ID {area_id!r}")
        for risk_id in (
            _require_list(node["risk_ids"], f"node {node_id}.risk_ids")
            if "risk_ids" in node
            else []
        ):
            if not isinstance(risk_id, str) or not RISK_ID.fullmatch(risk_id):
                _fail(f"node {node_id} has malformed risk ID {risk_id!r}")

    for area_id in AREA_IDS:
        if nodes[area_id].get("kind") != "area":
            _fail(f"{area_id} must be an area node")

    for index, edge in enumerate(_require_list(graph.get("edges"), "edges")):
        edge = _require_mapping(edge, f"edges[{index}]")
        if edge.get("from") not in nodes or edge.get("to") not in nodes:
            _fail(f"edges[{index}] has an unknown endpoint")
        if edge.get("type") not in relation_types:
            _fail(
                f"edges[{index}] has unknown relationship type "
                + repr(edge.get("type"))
            )

    release_prep = _require_mapping(
        graph.get("release_preparation"), "release_preparation"
    )
    if release_prep.get("task_id") != "indexly-release-prep":
        _fail("release_preparation.task_id must be indexly-release-prep")
    for index, path in enumerate(
        _require_list(
            release_prep.get("release_inputs"),
            "release_preparation.release_inputs",
        )
    ):
        _validate_relative_path(
            repository_root,
            path,
            f"release_preparation.release_inputs[{index}]",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph",
        type=Path,
        default=DEFAULT_GRAPH,
        help="path to the graph YAML",
    )
    args = parser.parse_args(argv)
    try:
        validate_graph(args.graph.resolve())
    except ValueError as exc:
        print(f"documentation graph validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Validated documentation graph: {args.graph}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
