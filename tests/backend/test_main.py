import re
from unittest.mock import MagicMock, patch
import pytest
from pathlib import Path
from app.main import (
    find_event_pairs,
    create_timeline_events,
    app,
)


@pytest.fixture
def client():
    app.config.update({"TESTING": True})
    with app.test_client() as client:
        yield client


def test_find_event_pairs_mutex_unmatched(app_logger):
    """Tests the logic for finding create/unlock and unmatched events."""
    timeline_events = [
        {
            "timestamp": "1",
            "mutex": "lock1",
            "event_name": "mutex_create",
            "type": "mutex",
        },
        {
            "timestamp": "2",
            "mutex": "lock2",
            "event_name": "mutex_create",
            "type": "mutex",
        },
        {
            "timestamp": "3",
            "mutex": "lock2",
            "event_name": "mutex_unlock",
            "type": "mutex",
        },
        {
            "timestamp": "4",
            "mutex": "lock1",
            "event_name": "mutex_unlock",
            "type": "mutex",
        },
        {
            "timestamp": "5",
            "mutex": "lock3",
            "event_name": "mutex_create",
            "type": "mutex",
        },
        {
            "timestamp": "6",
            "mutex": "lock4",
            "event_name": "mutex_unlock",
            "type": "mutex",
        },
    ]

    all_pairs, count = find_event_pairs(timeline_events, app_logger)

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


def test_find_event_pairs_mutex_create_one_to_many(app_logger):
    """
    Tests that multiple unlock events are paired with the single most recent create event.
    """
    timeline_events = [
        {
            "timestamp": "1",
            "mutex": "lock1",
            "event_name": "mutex_create",
            "type": "mutex",
        },
        {
            "timestamp": "2",
            "mutex": "lock1",
            "event_name": "mutex_create",
            "type": "mutex",
        },
        {
            "timestamp": "3",
            "mutex": "lock1",
            "event_name": "mutex_unlock",
            "type": "mutex",
        },
        {
            "timestamp": "4",
            "mutex": "lock1",
            "event_name": "mutex_unlock",
            "type": "mutex",
        },
    ]
    all_pairs, _ = find_event_pairs(timeline_events, app_logger)
    # Should find 2 create/unlock pairs and 0 lock/unlock pairs
    assert len(all_pairs) == 2
    # Both unlocks pair with the most recent create event (at timestamp "2")
    assert all_pairs[0]["start_event"]["timestamp"] == "2"
    assert all_pairs[0]["end_event"]["timestamp"] == "3"
    assert all_pairs[1]["start_event"]["timestamp"] == "2"
    assert all_pairs[1]["end_event"]["timestamp"] == "4"


def test_find_event_pairs_mutex_lock_nested(app_logger):
    """Tests correct pairing of nested lock/unlock events."""
    timeline_events = [
        {
            "timestamp": "1",
            "mutex": "lock1",
            "event_name": "mutex_lock",
            "type": "mutex",
        },
        {
            "timestamp": "2",
            "mutex": "lock1",
            "event_name": "mutex_lock",
            "type": "mutex",
        },
        {
            "timestamp": "3",
            "mutex": "lock1",
            "event_name": "mutex_unlock",
            "type": "mutex",
        },
        {
            "timestamp": "4",
            "mutex": "lock1",
            "event_name": "mutex_unlock",
            "type": "mutex",
        },
    ]
    all_pairs, _ = find_event_pairs(timeline_events, app_logger)
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


def test_find_event_pairs_barrier_one_to_many(app_logger):
    """Tests that multiple barrier_wait events are paired with one barrier_create."""
    timeline_events = [
        {
            "timestamp": "1",
            "barrier": "b1",
            "event_name": "barrier_create",
            "type": "barrier",
        },
        {
            "timestamp": "2",
            "barrier": "b1",
            "event_name": "barrier_wait",
            "type": "barrier",
        },
        {
            "timestamp": "3",
            "barrier": "b1",
            "event_name": "barrier_wait",
            "type": "barrier",
        },
    ]
    all_pairs, count = find_event_pairs(timeline_events, app_logger)

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


def test_find_event_pairs_ignores_events_without_name(app_logger):
    """Tests that events without a mutex/barrier name are ignored."""
    timeline_events = [
        {
            "timestamp": "1",
            "event_name": "mutex_create",
            "type": "mutex",
        },  # No mutex name
        {
            "timestamp": "2",
            "event_name": "barrier_create",
            "type": "barrier",
        },  # No barrier name
    ]
    all_pairs, count = find_event_pairs(timeline_events, app_logger)

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


@patch("app.main.OpenQAClientWrapper")
def test_analyze_log_cache_hit(mock_client_wrapper, client, tmp_path):
    """
    Tests that a second call to /analyze for the same job results in a log cache hit.
    """
    # 1. Setup
    mock_client_instance = MagicMock()
    mock_client_instance.hostname = "fake_host"
    mock_client_instance.job_id = "1"
    mock_client_instance.get_job_details.return_value = {
        "id": "1",
        "name": "fake_job",
        "state": "done",
        "children": {},
        "parents": {},
    }

    # The new download method doesn't return content, it writes to a file.
    # We can mock its behavior to simulate the file creation.
    def mock_download(job_id, filename, dest_path):
        Path(dest_path).write_text("This is a fake log.")

    mock_client_instance.download_log_to_file = MagicMock(side_effect=mock_download)
    mock_client_instance.get_job_url.return_value = "http://fake/t1"
    mock_client_wrapper.return_value = mock_client_instance
    mock_client_wrapper.return_value.autoinst_log_parsers = []
    with patch("app.main.CACHE_DIR", str(tmp_path)):
        # 2. First call (populate cache)
        res1 = client.post("/analyze", json={"log_url": "http://fake/tests/1"})
        assert res1.status_code == 200
        # Assert that the download method was called
        mock_client_instance.download_log_to_file.assert_called_once()

        # 3. Second call (should hit cache)
        mock_client_instance.download_log_to_file.reset_mock()
        res2 = client.post("/analyze", json={"log_url": "http://fake/tests/1"})
        assert res2.status_code == 200

        # 4. Assertions
        mock_client_instance.download_log_to_file.assert_not_called()

        debug_messages = [log["message"] for log in res2.get_json()["debug_log"]]
        assert "Cache hit for job 1." in debug_messages
        assert "Cache hit for log file 'autoinst-log.txt' of job 1." in debug_messages


@patch("app.main.openQACache")
@patch("app.main.OpenQAClientWrapper")
def test_analyze_cache_write(MockClient, MockCache, client, tmp_path):
    """
    Tests that cache.write_data is called on a cache miss for the log file.
    """
    mock_job_details = {
        "id": "1",
        "name": "fake_job",
        "state": "done",
        "children": {},
        "parents": {},
    }

    with patch("app.main.CACHE_DIR", str(tmp_path)):
        mock_client_instance = MockClient.return_value
        mock_client_instance.get_job_details.return_value = mock_job_details
        mock_client_instance.hostname = "fake_host"
        mock_client_instance.job_id = "1"
        mock_client_instance.get_job_url.return_value = "http://fake/t1"

        def mock_download(job_id, filename, dest_path):
            # This side effect simulates the download by creating a file
            Path(dest_path).write_text("This is a fake log.")

        mock_client_instance.download_log_to_file.side_effect = mock_download

        mock_cache_instance = MockCache.return_value
        mock_cache_instance.is_details_cached.return_value = False
        mock_cache_instance.get_job_details.return_value = None
        mock_cache_instance.get_cached_log_filepath.return_value = None

        # Make the call to the endpoint
        response = client.post("/analyze", json={"log_url": "http://fake/tests/1"})

        # Assertions
        assert response.status_code == 200
        mock_client_instance.get_job_details.assert_called_once_with("1")
        mock_client_instance.download_log_to_file.assert_called_once()
        mock_cache_instance.write_details.assert_called_once_with(
            "1", mock_job_details, log_files=["autoinst-log.txt"]
        )
