import re
from unittest.mock import MagicMock
from app.main import find_mutex_pairs, create_timeline_events, format_job_name


def test_format_job_name(monkeypatch):
    """Tests that job names are formatted correctly based on parser regex."""
    # Mock the global autoinst_log_parsers
    mock_parsers = [
        {
            "name": "memoleilnomemio",
            "match_name": re.compile(r".*(?P<name>folletto_?sonoio|\d?inumaforesta?_?\d+).*"),
        }
    ]
    monkeypatch.setattr("app.main.autoinst_log_parsers", mock_parsers)

    assert format_job_name("arch:x86_64:inumaforesta1") == "inumaforesta1"
    assert format_job_name("arch:x86_64:folletto_sonoio") == "folletto_sonoio"
    assert format_job_name("e_tanti_amici_ho") == "e_tanti_amici_ho"
    assert format_job_name("") == "Unknown Name"


def test_find_mutex_pairs():
    """Tests the logic for finding mutex create/unlock pairs."""
    timeline_events = [
        {"timestamp": "1", "mutex": "lock1", "event_name": "mutex_create"},
        {"timestamp": "2", "mutex": "lock2", "event_name": "mutex_create"},
        {"timestamp": "3", "mutex": "lock2", "event_name": "mutex_unlock"},
        {"timestamp": "4", "mutex": "lock1", "event_name": "mutex_unlock"},
        {"timestamp": "5", "mutex": "lock3", "event_name": "mutex_create"}, # Unmatched create
        {"timestamp": "6", "mutex": "lock4", "event_name": "mutex_unlock"}, # Unmatched unlock
    ]

    pairs, count = find_mutex_pairs(timeline_events)

    assert count == 6
    assert len(pairs) == 2

    # Check lock2 pair
    assert pairs[0]["mutex"] == "lock2"
    assert pairs[0]["start_event"]["timestamp"] == "2"
    assert pairs[0]["end_event"]["timestamp"] == "3"

    # Check lock1 pair
    assert pairs[1]["mutex"] == "lock1"
    assert pairs[1]["start_event"]["timestamp"] == "1"
    assert pairs[1]["end_event"]["timestamp"] == "4"


def test_find_mutex_pairs_nested():
    """Tests correct handling of nested mutex locks."""
    timeline_events = [
        {"timestamp": "1", "mutex": "lock1", "event_name": "mutex_create"},
        {"timestamp": "2", "mutex": "lock1", "event_name": "mutex_create"},
        {"timestamp": "3", "mutex": "lock1", "event_name": "mutex_unlock"},
        {"timestamp": "4", "mutex": "lock1", "event_name": "mutex_unlock"},
    ]
    pairs, _ = find_mutex_pairs(timeline_events)
    assert len(pairs) == 2
    # Inner pair
    assert pairs[0]["start_event"]["timestamp"] == "2"
    assert pairs[0]["end_event"]["timestamp"] == "3"
    # Outer pair
    assert pairs[1]["start_event"]["timestamp"] == "1"
    assert pairs[1]["end_event"]["timestamp"] == "4"


def test_create_timeline_events():
    """Tests the creation and sorting of the main timeline."""
    all_job_details = {
        "job1": {
            "autoinst-log": [
                {"timestamp": "2025-09-01T10:00:02Z", "message": "event 2"},
                {"timestamp": "2025-09-01T10:00:00Z", "message": "event 1"},
            ]
        },
        "job2": {
            "autoinst-log": [
                {"timestamp": "2025-09-01T10:00:01Z", "message": "event 3"},
                {"message": "event without timestamp"},  # Should be ignored
            ]
        },
        "job3": {"error": "some error"},  # Should be ignored
    }

    timeline = create_timeline_events(all_job_details)

    assert len(timeline) == 3

    # Check correct sorting
    assert timeline[0]["timestamp"] == "2025-09-01T10:00:00Z"
    assert timeline[1]["timestamp"] == "2025-09-01T10:00:01Z"
    assert timeline[2]["timestamp"] == "2025-09-01T10:00:02Z"

    # Check that job_id and log_index are added
    assert timeline[0]["job_id"] == "job1"
    assert timeline[0]["log_index"] == 1
    assert timeline[1]["job_id"] == "job2"
    assert timeline[1]["log_index"] == 0
    assert timeline[2]["job_id"] == "job1"
    assert timeline[2]["log_index"] == 0
