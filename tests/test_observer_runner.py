from pathlib import Path

import indexly.observers.runner as runner_module
from indexly.observers.runner import _snapshot_identity, run_observers


class DependencyObserver:
    name = "dependency"
    dependencies = []

    def __init__(self, calls):
        self.calls = calls

    def applies_to(self, file_path, metadata):
        return True

    def extract(self, file_path, metadata):
        self.calls.append("dependency.extract")
        return {"field": "new"}

    def compare(self, old, new):
        self.calls.append("dependency.compare")
        return [{"type": "FIELD_CHANGED", "field": "field", "old": "old", "new": "new"}]

    def format_event(self, event):
        return event["type"]


class DependentObserver:
    name = "dependent"
    dependencies = ["dependency"]

    def __init__(self, calls):
        self.calls = calls
        self.dependency_output = None

    def applies_to(self, file_path, metadata):
        return True

    def set_dependency_output(self, observer_name, old_state, new_state, events):
        self.calls.append(f"dependent.received.{observer_name}")
        self.dependency_output = (old_state, new_state, events)

    def extract(self, file_path, metadata):
        self.calls.append("dependent.extract")
        return self.dependency_output[1]

    def compare(self, old, new):
        self.calls.append("dependent.compare")
        return [{"type": "DOMAIN_EVENT"}]

    def format_event(self, event):
        return event["type"]


def test_observer_dependency_execution_order(monkeypatch, tmp_path):
    calls = []
    source = tmp_path / "file.txt"
    source.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(
        runner_module,
        "get_enabled_observers",
        lambda: [DependentObserver(calls), DependencyObserver(calls)],
    )
    monkeypatch.setattr(
        runner_module,
        "load_snapshot",
        lambda observer_name, raw_path: (
            {"field": "old"} if observer_name == "dependency" else None
        ),
    )
    monkeypatch.setattr(runner_module, "save_snapshot", lambda *args, **kwargs: None)

    events = run_observers(Path(source), {"hash": "hash"})

    assert calls == [
        "dependency.extract",
        "dependency.compare",
        "dependent.received.dependency",
        "dependent.extract",
        "dependent.compare",
    ]
    assert [event["type"] for event in events] == ["FIELD_CHANGED", "DOMAIN_EVENT"]


def test_snapshot_identity_uses_health_patient_id():
    assert _snapshot_identity({"patient_id": "P001", "entity_key": "report"}) == "P001"
    assert _snapshot_identity({"identity": "custom", "patient_id": "P001"}) == "custom"
