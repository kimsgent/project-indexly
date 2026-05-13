from indexly.observers.health.health_events import HealthEventObserver


def test_compare_emits_domain_events():
    observer = HealthEventObserver()

    events = observer.compare(
        {"patient_name": "John Doe", "address": "Old St"},
        {"patient_name": "Jane Doe", "address": "New St"},
    )

    assert [event["type"] for event in events] == [
        "PATIENT_NAME_UPDATED",
        "PATIENT_ADDRESS_UPDATED",
    ]


def test_dependency_events_are_translated():
    observer = HealthEventObserver()
    observer.set_dependency_output(
        "health_fields",
        {"dob": "1970-01-01"},
        {"dob": "1971-01-01"},
        [
            {
                "type": "DOB_CHANGED",
                "field": "dob",
                "old": "1970-01-01",
                "new": "1971-01-01",
            }
        ],
    )

    assert observer.extract(None, {}) == {"dob": "1971-01-01"}
    assert observer.compare({}, {"dob": "1971-01-01"}) == [
        {
            "type": "PATIENT_DOB_CORRECTED",
            "field": "dob",
            "old": "1970-01-01",
            "new": "1971-01-01",
        }
    ]


def test_format_event_renders_domain_event_name():
    rendered = HealthEventObserver().format_event(
        {
            "type": "PATIENT_ADDRESS_UPDATED",
            "field": "address",
            "old": "Old St",
            "new": "New St",
        }
    )

    assert "PATIENT_ADDRESS_UPDATED" in rendered
