import re
from unittest.mock import MagicMock
import pytest
from app.main import find_event_pairs, create_timeline_events, format_job_name


def test_format_job_name(monkeypatch):
    """Tests that job names are formatted correctly based on parser regex."""
    # Mock the app's logger to check for the warning
    mock_logger = MagicMock()
    monkeypatch.setattr("app.main.app.logger", mock_logger)
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


def test_find_event_pairs_mutex_unmatched():
    mock_logger = MagicMock()
    """Tests the logic for finding create/unlock and unmatched events."""
    timeline_events = [
        {"timestamp": "1", "mutex": "lock1", "event_name": "mutex_create", "type": "mutex"},
        {"timestamp": "2", "mutex": "lock2", "event_name": "mutex_create", "type": "mutex"},
        {"timestamp": "3", "mutex": "lock2", "event_name": "mutex_unlock", "type": "mutex"},
        {"timestamp": "4", "mutex": "lock1", "event_name": "mutex_unlock", "type": "mutex"},
        {"timestamp": "5", "mutex": "lock3", "event_name": "mutex_create", "type": "mutex"},
        {"timestamp": "6", "mutex": "lock4", "event_name": "mutex_unlock", "type": "mutex"},
    ]

    all_pairs, count = find_event_pairs(timeline_events, mock_logger)

    assert count == 6
    # Should find 2 create/unlock pairs and 0 lock/unlock pairs
    assert len(all_pairs) == 2

    # Check lock2 pair
    assert all_pairs[0]["mutex"] == "lock2"
    assert all_pairs[0]["start_event"]["timestamp"] == "2"
    assert all_pairs[0]["end_event"]["timestamp"] == "3"
    assert all_pairs[0]["pair_type"] == "mutex_create_unlock"

    # Check lock1 pair
    assert all_pairs[1]["mutex"] == "lock1"
    assert all_pairs[1]["start_event"]["timestamp"] == "1"
    assert all_pairs[1]["end_event"]["timestamp"] == "4"
    assert all_pairs[1]["pair_type"] == "mutex_create_unlock"


def test_find_event_pairs_mutex_create_one_to_many():
    mock_logger = MagicMock()
    """
    Tests that multiple unlock events are paired with the single most recent create event.
    """
    timeline_events = [
        {"timestamp": "1", "mutex": "lock1", "event_name": "mutex_create", "type": "mutex"},
        {"timestamp": "2", "mutex": "lock1", "event_name": "mutex_create", "type": "mutex"},
        {"timestamp": "3", "mutex": "lock1", "event_name": "mutex_unlock", "type": "mutex"},
        {"timestamp": "4", "mutex": "lock1", "event_name": "mutex_unlock", "type": "mutex"},
    ]
    all_pairs, _ = find_event_pairs(timeline_events, mock_logger)
    # Should find 2 create/unlock pairs and 0 lock/unlock pairs
    assert len(all_pairs) == 2
    # Both unlocks pair with the most recent create event (at timestamp "2")
    assert all_pairs[0]["start_event"]["timestamp"] == "2"
    assert all_pairs[0]["end_event"]["timestamp"] == "3"
    assert all_pairs[1]["start_event"]["timestamp"] == "2"
    assert all_pairs[1]["end_event"]["timestamp"] == "4"


def test_find_event_pairs_mutex_lock_nested():
    mock_logger = MagicMock()
    """Tests correct pairing of nested lock/unlock events."""
    timeline_events = [
        {"timestamp": "1", "mutex": "lock1", "event_name": "mutex_lock", "type": "mutex"},
        {"timestamp": "2", "mutex": "lock1", "event_name": "mutex_lock", "type": "mutex"},
        {"timestamp": "3", "mutex": "lock1", "event_name": "mutex_unlock", "type": "mutex"},
        {"timestamp": "4", "mutex": "lock1", "event_name": "mutex_unlock", "type": "mutex"},
    ]
    all_pairs, _ = find_event_pairs(timeline_events, mock_logger)
    # Should find 0 create/unlock pairs and 2 lock/unlock pairs
    assert len(all_pairs) == 2
    # Inner pair (LIFO)
    assert all_pairs[0]["start_event"]["timestamp"] == "2"
    assert all_pairs[0]["end_event"]["timestamp"] == "3"
    assert all_pairs[0]["pair_type"] == "mutex_lock_unlock"
    # Outer pair
    assert all_pairs[1]["start_event"]["timestamp"] == "1"
    assert all_pairs[1]["end_event"]["timestamp"] == "4"
    assert all_pairs[1]["pair_type"] == "mutex_lock_unlock"


def test_find_event_pairs_barrier_one_to_many():
    mock_logger = MagicMock()
    """Tests that multiple barrier_wait events are paired with one barrier_create."""
    timeline_events = [
        {"timestamp": "1", "barrier": "b1", "event_name": "barrier_create", "type": "barrier"},
        {"timestamp": "2", "barrier": "b1", "event_name": "barrier_wait", "type": "barrier"},
        {"timestamp": "3", "barrier": "b1", "event_name": "barrier_wait", "type": "barrier"},
    ]
    all_pairs, count = find_event_pairs(timeline_events, mock_logger)

    assert count == 3
    assert len(all_pairs) == 2

    # First wait event
    assert all_pairs[0]["barrier"] == "b1"
    assert all_pairs[0]["start_event"]["timestamp"] == "1"
    assert all_pairs[0]["end_event"]["timestamp"] == "2"
    assert all_pairs[0]["pair_type"] == "barrier_create_wait"

    # Second wait event
    assert all_pairs[1]["barrier"] == "b1"
    assert all_pairs[1]["start_event"]["timestamp"] == "1"
    assert all_pairs[1]["end_event"]["timestamp"] == "3"
    assert all_pairs[1]["pair_type"] == "barrier_create_wait"


def test_find_event_pairs_ignores_events_without_name():
    """Tests that events without a mutex/barrier name are ignored."""
    mock_logger = MagicMock()
    timeline_events = [
        {"timestamp": "1", "event_name": "mutex_create", "type": "mutex"},  # No mutex name
        {"timestamp": "2", "event_name": "barrier_create", "type": "barrier"}, # No barrier name
    ]
    all_pairs, count = find_event_pairs(timeline_events, mock_logger)

    assert len(all_pairs) == 0
    assert count == 0

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
