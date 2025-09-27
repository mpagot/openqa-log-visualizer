import re
from unittest.mock import MagicMock, patch
import pytest
from pathlib import Path
from app.main import (
    _parse_log_content,
    find_event_pairs,
    create_timeline_events,
    format_job_name,
    app,
)


@pytest.fixture
def client():
    app.config.update({"TESTING": True})
    with app.test_client() as client:
        yield client


def test_format_job_name(monkeypatch):
    """Tests that job names are formatted correctly based on parser regex."""
    # Mock the app's logger to check for the warning
    mock_logger = MagicMock()
    monkeypatch.setattr("app.main.app.logger", mock_logger)
    # Mock the global autoinst_log_parsers
    mock_parsers = [
        {
            "name": "memoleilnomemio",
            "match_name": re.compile(
                r".*(?P<name>folletto_?sonoio|\d?inumaforesta?_?\d+).*"
            ),
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


def test_parse_log_content(tmp_path, monkeypatch):
    """
    Tests that _parse_log_content correctly reads a file and parses its content.
    """
    # 1. Setup
    log_file = tmp_path / "autoinst.txt"
    log_file.write_text("[2025-09-18T10:00:00.123] <1> [some_channel] some message")

    job_details = {"name": "fake_job_for_parser"}
    performance_metrics = {"log_parsing": []}
    job_id = "777"

    # Mock the parsers used by the function
    mock_parser = {
        "name": "test_parser",
        "match_name": re.compile(".*"),
        "channels": [
            {
                "name": "some_channel",
                "type": "some_type",
                "pattern": re.compile(r"\[some_channel\] (?P<content>.*)"),
            }
        ],
    }
    monkeypatch.setattr("app.main.autoinst_log_parsers", [mock_parser])
    monkeypatch.setattr("app.main.timestamp_re", re.compile(r"^\[(?P<timestamp>\S+)\]"))
    monkeypatch.setattr("app.main.perl_exception_re", re.compile(r"NEVER_MATCH"))

    # 2. Call the function with a file path
    _parse_log_content(job_details, str(log_file), job_id, performance_metrics)

    # 3. Assertions
    assert "autoinst-log" in job_details
    parsed_log = job_details["autoinst-log"]
    assert len(parsed_log) == 1
    assert parsed_log[0]["message"] == "<1> [some_channel] some message"
    assert parsed_log[0]["content"] == "some message"
    assert parsed_log[0]["event_name"] == "some_channel"
    assert len(performance_metrics["log_parsing"]) == 1
    assert performance_metrics["log_parsing"][0]["job_id"] == job_id


def test_find_event_pairs_ignores_events_without_name():
    """Tests that events without a mutex/barrier name are ignored."""
    mock_logger = MagicMock()
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
        mock_cache_instance.hit.return_value = False
        mock_cache_instance.get_data.return_value = None
        mock_cache_instance.get_log_content.return_value = (None, False)

        # Define a valid path for the log file to be written to
        log_file_path = tmp_path / "autoinst-log.txt"
        mock_cache_instance.get_log_path.return_value = str(log_file_path)

        # Make the call to the endpoint
        response = client.post("/analyze", json={"log_url": "http://fake/tests/1"})

        # Assertions
        assert response.status_code == 200
        mock_client_instance.get_job_details.assert_called_once_with("1")
        mock_client_instance.download_log_to_file.assert_called_once()
        mock_cache_instance.write_metadata.assert_called_once_with(
            "1", mock_job_details, log_files=["autoinst-log.txt"]
        )
