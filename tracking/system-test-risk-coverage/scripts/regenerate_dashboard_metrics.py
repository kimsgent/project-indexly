#!/usr/bin/env python3
"""Regenerate the local Indexly quality dashboard metrics.

The dated worksheet JSON files under test-cases/ are the source of truth. This
script rebuilds dashboard/metrics.json from those worksheets so historical
trend data stays reproducible and file-based.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


AREA_IDS = [f"IDX-{number:02d}" for number in range(1, 13)]
CONFIRMED_DEFECT_TYPES = {"Defect", "Regression"}
MITIGATED_STATUSES = {"Mitigated", "Closed"}
OPEN_STATUSES = {"Open", "In Progress"}
EXECUTED_CASE_STATUSES = {"Pass", "Warn", "Fail"}
CASE_STATUS_KEYS = {
    "Pass": "pass_count",
    "Warn": "warn_count",
    "Fail": "fail_count",
    "Skip": "skip_count",
    "Collected": "collected_count",
}
RUN_FOLDER_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-test-case-[a-z0-9-]+$")
WORKSHEET_PATTERN = "system-test-case-summary-worksheet-*.json"


class TrackingMetricsError(Exception):
    """Raised when tracking inputs cannot produce a valid dashboard."""


def parse_args() -> argparse.Namespace:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Regenerate Project-Indexly system-test risk dashboard metrics."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help="Path to tracking/system-test-risk-coverage.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output metrics JSON path. Defaults to <root>/dashboard/metrics.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that the current metrics.json already matches generated output.",
    )
    return parser.parse_args()


def as_date(value: Any, *, field: str, path: Path) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise TrackingMetricsError(f"{path}: {field} must be a YYYY-MM-DD string.")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise TrackingMetricsError(f"{path}: {field} must be a valid YYYY-MM-DD date.") from exc


def percent(numerator: int, denominator: int) -> int | float | None:
    if denominator == 0:
        return None
    value = round((numerator / denominator) * 100, 2)
    return int(value) if value.is_integer() else value


def average(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def normalize_status(value: Any) -> str:
    if value in (None, ""):
        return "Unknown"
    normalized = re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", str(value).strip())).lower()
    status_map = {
        "open": "Open",
        "in progress": "In Progress",
        "mitigated": "Mitigated",
        "closed": "Closed",
        "pass": "Pass",
        "warn": "Warn",
        "fail": "Fail",
        "skip": "Skip",
        "collected": "Collected",
        "unknown": "Unknown",
    }
    return status_map.get(normalized, normalized.title())


def normalize_type(value: Any) -> str:
    if value in (None, ""):
        return "Unknown"
    normalized = re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", str(value).strip())).lower()
    type_map = {
        "defect": "Defect",
        "regression": "Regression",
    }
    return type_map.get(normalized, normalized.title())


def empty_area_counts() -> dict[str, int]:
    return {area_id: 0 for area_id in AREA_IDS}


def load_worksheets(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    test_cases_dir = root / "test-cases"
    if not test_cases_dir.exists():
        raise TrackingMetricsError(f"Missing test-cases directory: {test_cases_dir}")

    worksheet_paths = sorted(test_cases_dir.glob(f"*/{WORKSHEET_PATTERN}"))
    if not worksheet_paths:
        raise TrackingMetricsError(
            f"No dated worksheet JSON files found under {test_cases_dir}. "
            "Create a run-specific folder before regenerating dashboard metrics."
        )

    worksheets: list[tuple[Path, dict[str, Any]]] = []
    for path in worksheet_paths:
        if not RUN_FOLDER_PATTERN.match(path.parent.name):
            raise TrackingMetricsError(
                f"{path}: worksheet JSON must live in a dated run folder named "
                "YYYY-MM-DD-test-case-<area-or-change>."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TrackingMetricsError(f"{path}: invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise TrackingMetricsError(f"{path}: worksheet JSON root must be an object.")
        validate_worksheet(path, data)
        worksheets.append((path, data))

    return sorted(
        worksheets,
        key=lambda item: (item[1].get("created_date", ""), str(item[0]).lower()),
    )


def validate_worksheet(path: Path, data: dict[str, Any]) -> None:
    required = [
        "schema",
        "worksheet_id",
        "created_date",
        "cases",
        "defects_identified",
        "metrics_snapshot",
    ]
    for field in required:
        if field not in data:
            raise TrackingMetricsError(f"{path}: missing required field '{field}'.")

    schema = data["schema"]
    if not isinstance(schema, str) or not schema.startswith(
        "indexly.tracking.system_test_case_summary_worksheet."
    ):
        raise TrackingMetricsError(f"{path}: schema is not an Indexly worksheet schema.")

    as_date(data["created_date"], field="created_date", path=path)
    if not isinstance(data["cases"], list):
        raise TrackingMetricsError(f"{path}: cases must be a list.")
    if not isinstance(data["defects_identified"], list):
        raise TrackingMetricsError(f"{path}: defects_identified must be a list.")
    if not isinstance(data["metrics_snapshot"], dict):
        raise TrackingMetricsError(f"{path}: metrics_snapshot must be an object.")

    for index, case in enumerate(data["cases"]):
        if not isinstance(case, dict):
            raise TrackingMetricsError(f"{path}: every case entry must be an object.")
        as_date(case.get("plan_date"), field=f"cases[{index}].plan_date", path=path)
        as_date(case.get("actual_date"), field=f"cases[{index}].actual_date", path=path)

    for index, defect in enumerate(data["defects_identified"]):
        if not isinstance(defect, dict):
            raise TrackingMetricsError(f"{path}: every defect entry must be an object.")
        as_date(
            defect.get("detected_date"),
            field=f"defects_identified[{index}].detected_date",
            path=path,
        )
        as_date(
            defect.get("mitigated_date"),
            field=f"defects_identified[{index}].mitigated_date",
            path=path,
        )


def relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def case_date(case: dict[str, Any], worksheet_date: str) -> str:
    return str(case.get("actual_date") or case.get("plan_date") or worksheet_date)


def defect_date(defect: dict[str, Any], worksheet_date: str) -> str:
    return str(defect.get("detected_date") or worksheet_date)


def rpn_value(record: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                return int(stripped)
    return None


def risk_ids_for(defect: dict[str, Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()

    def add_candidate(candidate: Any) -> None:
        normalized = str(candidate).strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        deduped.append(normalized)

    risk_ids = defect.get("related_risk_ids")
    if isinstance(risk_ids, list):
        for risk_id in risk_ids:
            add_candidate(risk_id)
        if deduped:
            return deduped
    risk_id = defect.get("risk_id")
    if risk_id:
        add_candidate(risk_id)
    return deduped


def build_metrics(root: Path) -> dict[str, Any]:
    worksheets = load_worksheets(root)
    generated_from = [relative_to_root(path, root) for path, _ in worksheets]
    cases: list[dict[str, Any]] = []
    defects: list[dict[str, Any]] = []

    for path, worksheet in worksheets:
        worksheet_date = str(worksheet["created_date"])
        for case in worksheet["cases"]:
            cases.append({**case, "_worksheet_date": worksheet_date})
        for defect in worksheet["defects_identified"]:
            defects.append({**defect, "_worksheet_date": worksheet_date})

    confirmed_defects = [
        defect
        for defect in defects
        if normalize_type(defect.get("defect_type")) in CONFIRMED_DEFECT_TYPES
    ]

    defects_by_area = empty_area_counts()
    open_defects_by_area = empty_area_counts()
    regressions_by_area = empty_area_counts()
    rpn_by_area: dict[str, list[int]] = {area_id: [] for area_id in AREA_IDS}
    defects_by_risk = Counter()
    risk_details: dict[str, dict[str, Any]] = {}
    high_risk_open: list[dict[str, Any]] = []
    regression_chains: list[dict[str, Any]] = []
    mitigation_durations: list[int] = []

    for defect in confirmed_defects:
        area_id = str(defect.get("area_id") or "Unknown")
        status = normalize_status(defect.get("mitigation_status") or defect.get("status"))
        defect_type = normalize_type(defect.get("defect_type"))
        detected = as_date(
            defect.get("detected_date") or defect.get("_worksheet_date"),
            field="detected_date",
            path=Path(str(defect.get("defect_id") or "defect")),
        )
        mitigated = as_date(
            defect.get("mitigated_date"),
            field="mitigated_date",
            path=Path(str(defect.get("defect_id") or "defect")),
        )
        rpn = rpn_value(defect, "rpn")

        if area_id in defects_by_area:
            defects_by_area[area_id] += 1
            if rpn is not None:
                rpn_by_area[area_id].append(rpn)
            if defect_type == "Regression":
                regressions_by_area[area_id] += 1

        if status in OPEN_STATUSES and area_id in open_defects_by_area:
            open_defects_by_area[area_id] += 1

        if status in OPEN_STATUSES and rpn is not None and 1 <= rpn <= 5:
            high_risk_open.append(
                {
                    "defect_id": defect.get("defect_id", ""),
                    "area_id": area_id,
                    "risk_ids": risk_ids_for(defect),
                    "rpn": rpn,
                    "detected_date": detected.isoformat() if detected else "",
                    "summary": defect.get("summary", ""),
                }
            )

        if detected and mitigated and status in MITIGATED_STATUSES:
            mitigation_durations.append((mitigated - detected).days)

        for risk_id in risk_ids_for(defect):
            defects_by_risk[risk_id] += 1
            detail = risk_details.setdefault(
                risk_id,
                {
                    "risk_id": risk_id,
                    "area_ids": set(),
                    "count": 0,
                    "rpn_values": [],
                    "latest_detected_date": "",
                },
            )
            detail["count"] += 1
            if area_id:
                detail["area_ids"].add(area_id)
            if rpn is not None:
                detail["rpn_values"].append(rpn)
            if detected and detected.isoformat() > detail["latest_detected_date"]:
                detail["latest_detected_date"] = detected.isoformat()

        regression_of = defect.get("regression_of")
        if regression_of:
            regression_chains.append(
                {
                    "regression_of": regression_of,
                    "defect_id": defect.get("defect_id", ""),
                    "area_id": area_id,
                    "detected_date": detected.isoformat() if detected else "",
                    "rpn": rpn,
                    "summary": defect.get("summary", ""),
                }
            )

    case_counts = Counter()
    test_execution_by_date: dict[str, Counter[str]] = defaultdict(Counter)
    for case in cases:
        status = normalize_status(case.get("status"))
        if status in CASE_STATUS_KEYS:
            case_counts[CASE_STATUS_KEYS[status]] += 1
        if status != "Collected":
            case_counts["planned_cases"] += 1
        if status in EXECUTED_CASE_STATUSES:
            case_counts["executed_cases"] += 1

        date_key = case_date(case, str(case.get("_worksheet_date")))
        daily = test_execution_by_date[date_key]
        if status != "Collected":
            daily["planned_cases"] += 1
        if status in EXECUTED_CASE_STATUSES:
            daily["executed_cases"] += 1
        if status in CASE_STATUS_KEYS:
            daily[CASE_STATUS_KEYS[status]] += 1

    mitigated_count = sum(
        1
        for defect in confirmed_defects
        if normalize_status(defect.get("mitigation_status") or defect.get("status"))
        in MITIGATED_STATUSES
    )
    open_count = sum(
        1
        for defect in confirmed_defects
        if normalize_status(defect.get("mitigation_status") or defect.get("status"))
        in OPEN_STATUSES
    )
    high_risk_open_count = len(high_risk_open)

    repeated_risks = []
    for risk_id, detail in sorted(risk_details.items()):
        if detail["count"] <= 1:
            continue
        rpn_values = detail["rpn_values"]
        area_ids = sorted(detail["area_ids"])
        repeated_risks.append(
            {
                "risk_id": risk_id,
                "area_id": ", ".join(area_ids),
                "area_ids": area_ids,
                "count": detail["count"],
                "lowest_rpn": min(rpn_values) if rpn_values else None,
                "latest_detected_date": detail["latest_detected_date"],
            }
        )

    performance_over_time = build_performance_series(confirmed_defects)
    test_execution_over_time = []
    for date_key in sorted(test_execution_by_date):
        daily = test_execution_by_date[date_key]
        test_execution_over_time.append(
            {
                "date": date_key,
                "planned_cases": daily["planned_cases"],
                "executed_cases": daily["executed_cases"],
                "pass_count": daily["pass_count"],
                "warn_count": daily["warn_count"],
                "fail_count": daily["fail_count"],
                "skip_count": daily["skip_count"],
                "collected_count": daily["collected_count"],
                "test_execution_rate_percent": percent(
                    daily["executed_cases"], daily["planned_cases"]
                ),
            }
        )

    mean_time = average(mitigation_durations)
    if mean_time is not None and float(mean_time).is_integer():
        mean_time = int(mean_time)

    generated_at = max((str(worksheet["created_date"]) for _, worksheet in worksheets), default=None)
    if generated_at is None:
        generated_at = date.today().isoformat()

    metrics: dict[str, Any] = {
        "schema": "indexly.tracking.quality_dashboard_metrics.v1",
        "generated_at": generated_at,
        "generated_from": generated_from,
        "notes": [
            "Generated from dated worksheet JSON artifacts under test-cases/.",
            "Do not edit baseline seed documents for run-specific outcomes; create a new dated run folder from templates instead.",
        ],
        "summary": {
            "total_confirmed_defects": len(confirmed_defects),
            "mitigated_confirmed_defects": mitigated_count,
            "open_confirmed_defects": open_count,
            "mitigation_rate_percent": percent(mitigated_count, len(confirmed_defects)),
            "high_risk_open_defects": high_risk_open_count,
            "repeated_risk_count": len(repeated_risks),
            "planned_cases": case_counts["planned_cases"],
            "executed_cases": case_counts["executed_cases"],
            "pass_count": case_counts["pass_count"],
            "warn_count": case_counts["warn_count"],
            "fail_count": case_counts["fail_count"],
            "skip_count": case_counts["skip_count"],
            "collected_count": case_counts["collected_count"],
            "test_execution_rate_percent": percent(
                case_counts["executed_cases"], case_counts["planned_cases"]
            ),
            "mean_time_to_mitigate_days": mean_time,
        },
        "performance_over_time": performance_over_time,
        "test_execution_over_time": test_execution_over_time,
        "defects_by_area_id": defects_by_area,
        "open_defects_by_area_id": open_defects_by_area,
        "regressions_by_area_id": regressions_by_area,
        "average_rpn_by_area": {
            area_id: average(values) for area_id, values in rpn_by_area.items()
        },
        "lowest_rpn_by_area": {
            area_id: min(values) if values else None for area_id, values in rpn_by_area.items()
        },
        "defects_by_risk_id": dict(sorted(defects_by_risk.items())),
        "repeated_risks": repeated_risks,
        "regression_chains": regression_chains,
        "high_risk_open_defects": high_risk_open,
    }
    validate_metrics(metrics)
    return metrics


def build_performance_series(defects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dates: set[date] = set()
    normalized: list[dict[str, Any]] = []
    for defect in defects:
        detected = as_date(
            defect.get("detected_date") or defect.get("_worksheet_date"),
            field="detected_date",
            path=Path(str(defect.get("defect_id") or "defect")),
        )
        mitigated = as_date(
            defect.get("mitigated_date"),
            field="mitigated_date",
            path=Path(str(defect.get("defect_id") or "defect")),
        )
        if detected:
            dates.add(detected)
        if mitigated:
            dates.add(mitigated)
        normalized.append({**defect, "_detected": detected, "_mitigated": mitigated})

    series = []
    for sampled_date in sorted(dates):
        total = sum(1 for defect in normalized if defect["_detected"] and defect["_detected"] <= sampled_date)
        mitigated = sum(
            1
            for defect in normalized
            if defect["_mitigated"]
            and defect["_mitigated"] <= sampled_date
            and normalize_status(defect.get("mitigation_status") or defect.get("status"))
            in MITIGATED_STATUSES
        )
        open_count = sum(
            1
            for defect in normalized
            if defect["_detected"]
            and defect["_detected"] <= sampled_date
            and not (
                defect["_mitigated"]
                and defect["_mitigated"] <= sampled_date
                and normalize_status(defect.get("mitigation_status") or defect.get("status"))
                in MITIGATED_STATUSES
            )
        )
        high_risk_open = sum(
            1
            for defect in normalized
            if defect["_detected"]
            and defect["_detected"] <= sampled_date
            and not (
                defect["_mitigated"]
                and defect["_mitigated"] <= sampled_date
                and normalize_status(defect.get("mitigation_status") or defect.get("status"))
                in MITIGATED_STATUSES
            )
            and ((defect_rpn := rpn_value(defect, "rpn")) is not None and 1 <= defect_rpn <= 5)
        )
        series.append(
            {
                "date": sampled_date.isoformat(),
                "total_confirmed_defects": total,
                "mitigated_confirmed_defects": mitigated,
                "open_confirmed_defects": open_count,
                "mitigation_rate_percent": percent(mitigated, total),
                "high_risk_open_defects": high_risk_open,
            }
        )
    return series


def validate_metrics(metrics: dict[str, Any]) -> None:
    required = [
        "schema",
        "summary",
        "generated_at",
        "defects_by_area_id",
        "test_execution_over_time",
    ]
    for field in required:
        if field not in metrics:
            raise TrackingMetricsError(f"generated metrics missing required field '{field}'.")


def render_json(metrics: dict[str, Any]) -> str:
    return json.dumps(metrics, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    output = args.output.resolve() if args.output else root / "dashboard" / "metrics.json"

    try:
        metrics = build_metrics(root)
        rendered = render_json(metrics)
        if args.check:
            current = output.read_bytes().decode("utf-8") if output.exists() else ""
            if current != rendered:
                print(f"{output} is stale. Regenerate dashboard metrics.", file=sys.stderr)
                return 1
            print(f"{output} is up to date.")
            return 0

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered.encode("utf-8"))
        print(
            "Regenerated "
            f"{output} from {len(metrics['generated_from'])} worksheet JSON file(s)."
        )
        return 0
    except TrackingMetricsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
