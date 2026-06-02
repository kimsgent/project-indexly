import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "tracking"
    / "system-test-risk-coverage"
    / "scripts"
    / "regenerate_dashboard_metrics.py"
)


def load_metrics_module():
    spec = importlib.util.spec_from_file_location("tracking_metrics", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_worksheet(root: Path, run_folder: str, file_name: str, payload: dict) -> Path:
    target_dir = root / "test-cases" / run_folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / file_name
    target_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target_file


def minimal_worksheet(*, worksheet_id: str, created_date: str) -> dict:
    return {
        "schema": "indexly.tracking.system_test_case_summary_worksheet.v2",
        "worksheet_id": worksheet_id,
        "created_date": created_date,
        "cases": [],
        "defects_identified": [],
        "metrics_snapshot": {},
    }


def test_generated_at_uses_latest_worksheet_date(tmp_path: Path):
    module = load_metrics_module()
    root = tmp_path / "tracking"

    write_worksheet(
        root,
        "2026-05-01-test-case-alpha",
        "system-test-case-summary-worksheet-2026-05-01-alpha.json",
        minimal_worksheet(worksheet_id="A", created_date="2026-05-01"),
    )
    write_worksheet(
        root,
        "2026-05-02-test-case-beta",
        "system-test-case-summary-worksheet-2026-05-02-beta.json",
        minimal_worksheet(worksheet_id="B", created_date="2026-05-02"),
    )

    metrics = module.build_metrics(root)
    assert metrics["generated_at"] == "2026-05-02"


def test_status_and_risk_id_normalization_for_open_regression(tmp_path: Path):
    module = load_metrics_module()
    root = tmp_path / "tracking"
    worksheet = minimal_worksheet(worksheet_id="C", created_date="2026-05-03")
    worksheet["defects_identified"] = [
        {
            "defect_id": "IDX-05-DEF-007",
            "defect_type": " regression ",
            "mitigation_status": "in-progress",
            "area_id": "IDX-05",
            "rpn": " 5 ",
            "related_risk_ids": [" IDX-RISK-005 ", "", "IDX-RISK-005"],
            "detected_date": "2026-05-03",
        }
    ]

    write_worksheet(
        root,
        "2026-05-03-test-case-gamma",
        "system-test-case-summary-worksheet-2026-05-03-gamma.json",
        worksheet,
    )

    metrics = module.build_metrics(root)
    assert metrics["summary"]["open_confirmed_defects"] == 1
    assert metrics["summary"]["high_risk_open_defects"] == 1
    assert metrics["defects_by_risk_id"] == {"IDX-RISK-005": 1}


def test_invalid_case_date_is_rejected(tmp_path: Path):
    module = load_metrics_module()
    root = tmp_path / "tracking"
    worksheet = minimal_worksheet(worksheet_id="D", created_date="2026-05-04")
    worksheet["cases"] = [
        {
            "test_case_id": "1.001",
            "status": "Pass",
            "actual_date": "2026-13-99",
        }
    ]

    write_worksheet(
        root,
        "2026-05-04-test-case-delta",
        "system-test-case-summary-worksheet-2026-05-04-delta.json",
        worksheet,
    )

    with pytest.raises(module.TrackingMetricsError, match=r"cases\[0\]\.actual_date"):
        module.build_metrics(root)
