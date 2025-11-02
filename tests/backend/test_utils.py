import re
from unittest.mock import MagicMock, call, patch
import pytest

from app.utils import discover_jobs, format_job_name, process_job_logs


def test_format_job_name(app_logger):
    """Tests that job names are formatted correctly based on parser regex."""
    mock_parsers = [
        {
            "name": "parser1",
            # finds a sequence of one or more word characters or hyphens
            # that is surrounded by word boundaries (\b) and
            # delimited by colons (:), and captures this sequence into a group named "name".
            "match_name": re.compile(r".*:\b(?P<name>[\w-]+)\b:.*"),
        }
    ]

    assert (
        format_job_name("arch:x86_64:my-job-name:rest", mock_parsers, app_logger)
        == "my-job-name"
    )

    # Test with a non-matching name
    assert (
        format_job_name("non-matching-name", mock_parsers, app_logger)
        == "non-matching-name"
    )

    # Test with an empty name
    assert format_job_name("", mock_parsers, app_logger) == "Unknown Name"


def test_discover_jobs_no_children(app_logger):
    """Tests discovery with a single job that has no parallel relations."""
    mock_client = MagicMock()
    mock_cache = MagicMock()
    mock_client.get_job_details.return_value = {
        "id": "1",
        "name": "job1",
        "state": "done",
        "children": {},
        "parents": {},
    }
    mock_client.get_job_url.return_value = "http://localhost/t1"
    mock_cache.is_details_cached.return_value = False

    all_details, _, _ = discover_jobs(mock_client, mock_cache, "1", 10, app_logger)

    assert "1" in all_details
    assert len(all_details) == 1
    mock_client.get_job_details.assert_called_once_with("1")


def test_discover_jobs_cache_no_children(app_logger):
    """Tests discovery with a single job that has no parallel relations."""
    mock_client = MagicMock()
    mock_cache = MagicMock()
    details = {
        "id": "1",
        "name": "job1",
        "state": "done",
        "children": {},
        "parents": {},
    }
    # save it in both cache and client, but later ensure only cache is used
    mock_client.get_job_details.return_value = details
    mock_cache.get_job_details.return_value = details
    mock_client.get_job_url.return_value = "http://localhost/t1"
    mock_cache.is_details_cached.return_value = True

    all_details, _, _ = discover_jobs(mock_client, mock_cache, "1", 10, app_logger)

    assert len(all_details) == 1
    assert "1" in all_details
    # check that function mark it
    assert "is_cached" in all_details["1"]
    assert all_details["1"]["is_cached"]
    mock_cache.get_job_details.assert_called_once_with("1")
    mock_client.get_job_details.assert_not_called()


def test_discover_jobs_with_children_and_parents(app_logger):
    """Tests discovery of a job with both parallel children and parents."""
    mock_client = MagicMock()
    mock_cache = MagicMock()

    mock_client.get_job_details.side_effect = [
        {
            "id": "2",
            "name": "job2",
            "state": "done",
            "children": {"Parallel": ["3"]},
            "parents": {"Parallel": ["1"]},
        },
        {"id": "1", "name": "job1", "state": "done", "children": {}, "parents": {}},
        {"id": "3", "name": "job3", "state": "done", "children": {}, "parents": {}},
    ]
    mock_client.get_job_url.side_effect = [
        "http://localhost/t2",
        "http://localhost/t1",
        "http://localhost/t3",
    ]
    mock_cache.is_details_cached.return_value = False

    all_details, _, _ = discover_jobs(mock_client, mock_cache, "2", 10, app_logger)

    assert len(all_details) == 3
    assert "1" in all_details
    assert "2" in all_details
    assert "3" in all_details
    assert "job_url" in all_details["1"]
    assert "localhost" in all_details["1"]["job_url"]
    assert mock_client.get_job_details.call_count == 3
    mock_client.get_job_details.assert_has_calls(
        [call("2"), call("1"), call("3")], any_order=True
    )


def test_discover_jobs_cache_with_children_and_parents(app_logger):
    """Tests discovery of a job with both parallel children and parents."""
    mock_client = MagicMock()
    mock_cache = MagicMock()

    mock_cache.get_job_details.side_effect = [
        {
            "id": "2",
            "name": "job2",
            "state": "done",
            "children": {"Parallel": ["3"]},
            "parents": {"Parallel": ["1"]},
        },
        {"id": "1", "name": "job1", "state": "done", "children": {}, "parents": {}},
        {"id": "3", "name": "job3", "state": "done", "children": {}, "parents": {}},
    ]
    mock_client.get_job_url.side_effect = [
        "http://localhost/t2",
        "http://localhost/t1",
        "http://localhost/t3",
    ]
    mock_cache.is_details_cached.return_value = True

    all_details, _, _ = discover_jobs(mock_client, mock_cache, "2", 10, app_logger)

    assert len(all_details) == 3
    assert "1" in all_details
    assert "2" in all_details
    assert "3" in all_details
    assert "job_url" in all_details["1"]
    assert "localhost" in all_details["1"]["job_url"]
    assert mock_cache.get_job_details.call_count == 3
    mock_client.get_job_details.assert_not_called()


@pytest.mark.parametrize("cached", [True, False])
def test_discover_jobs_performance(cached, app_logger):
    """Tests discovery of a job with both parallel children and parents."""
    mock_client = MagicMock()
    mock_cache = MagicMock()

    details = [
        {
            "id": "2",
            "name": "job2",
            "state": "done",
            "children": {"Parallel": ["3"]},
            "parents": {"Parallel": ["1"]},
        },
        {"id": "1", "name": "job1", "state": "done", "children": {}, "parents": {}},
        {"id": "3", "name": "job3", "state": "done", "children": {}, "parents": {}},
    ]
    if cached:
        mock_cache.get_job_details.side_effect = details
    else:
        mock_client.get_job_details.side_effect = details

    mock_client.get_job_url.side_effect = [
        "http://localhost/t2",
        "http://localhost/t1",
        "http://localhost/t3",
    ]
    mock_cache.is_details_cached.return_value = cached

    all_details, performance, _ = discover_jobs(
        mock_client, mock_cache, "2", 10, app_logger
    )

    assert isinstance(performance, dict)
    assert "api_calls" in performance
    if cached:
        assert performance["job_details_cache_hits"] == len(all_details)


@pytest.mark.parametrize("cached", [True, False])
def test_discover_jobs_server_logs(cached, app_logger):
    """Tests discovery of a job with both parallel children and parents."""
    mock_client = MagicMock()
    mock_cache = MagicMock()

    details = [
        {
            "id": "2",
            "name": "job2",
            "state": "done",
            "children": {"Parallel": ["3"]},
            "parents": {"Parallel": ["1"]},
        },
        {"id": "1", "name": "job1", "state": "done", "children": {}, "parents": {}},
        {"id": "3", "name": "job3", "state": "done", "children": {}, "parents": {}},
    ]
    if cached:
        mock_cache.get_job_details.side_effect = details
    else:
        mock_client.get_job_details.side_effect = details
    mock_client.get_job_url.side_effect = [
        "http://localhost/t2",
        "http://localhost/t1",
        "http://localhost/t3",
    ]
    mock_cache.is_details_cached.return_value = cached

    _, _, server_logs = discover_jobs(mock_client, mock_cache, "2", 10, app_logger)

    assert isinstance(server_logs, list)


def test_discover_jobs_circular_dependency(app_logger):
    """Tests discovery of a job with both parallel children and parents.
    But dependency in details has a circular dependency loop.
    Function has not to loop forever"""
    mock_client = MagicMock()
    mock_cache = MagicMock()

    mock_client.get_job_details.side_effect = [
        {
            "id": "2",
            "name": "job2",
            "state": "done",
            "children": {"Parallel": ["3"]},
            "parents": {"Parallel": ["1"]},
        },
        {
            "id": "1",
            "name": "job1",
            "state": "done",
            "children": {"Parallel": ["2"]},
            "parents": {},
        },
        {"id": "3", "name": "job3", "state": "done", "children": {}, "parents": {}},
    ]
    mock_client.get_job_url.side_effect = [
        "http://localhost/t2",
        "http://localhost/t1",
        "http://localhost/t3",
    ]
    mock_cache.is_details_cached.return_value = False

    all_details, _, _ = discover_jobs(mock_client, mock_cache, "2", 10, app_logger)

    assert len(all_details) == 3


def test_discover_jobs_max_jobs_limit(app_logger):
    """Tests that job discovery stops when max_jobs is reached."""
    mock_client = MagicMock()
    mock_cache = MagicMock()

    details = [
        {
            "id": "1",
            "name": "job1",
            "state": "done",
            "children": {"Parallel": ["2", "3"]},
        },
        {"id": "2", "name": "job2", "state": "done", "children": {}, "parents": {}},
        {"id": "3", "name": "job3", "state": "done", "children": {}, "parents": {}},
    ]
    urls = ["http://localhost/t1", "http://localhost/t2", "something else"]

    mock_client.get_job_details.side_effect = details
    mock_client.get_job_url.side_effect = urls
    mock_cache.is_details_cached.return_value = False

    all_details, _, _ = discover_jobs(mock_client, mock_cache, "1", 3, app_logger)

    assert len(all_details) == 3
    assert "1" in all_details
    assert "2" in all_details
    assert "3" in all_details
    assert mock_client.get_job_details.call_count == 3
    mock_client.get_job_details.reset_mock()
    mock_client.get_job_details.side_effect = details
    mock_client.get_job_url.side_effect = urls

    all_details, _, _ = discover_jobs(mock_client, mock_cache, "1", 2, app_logger)

    assert len(all_details) == 2
    assert "1" in all_details
    assert "2" in all_details
    assert "3" not in all_details
    assert mock_client.get_job_details.call_count == 2


def test_process_job_logs_nothing(app_logger):
    mock_client = MagicMock()
    mock_cache = MagicMock()

    all_job_details, performance_metrics, server_log = process_job_logs(
        mock_client, mock_cache, {}, [], app_logger
    )

    assert isinstance(all_job_details, dict)
    assert len(all_job_details.keys()) == 0


def test_process_job_logs_invalid_details(app_logger):
    mock_client = MagicMock()
    mock_cache = MagicMock()
    in_details = {"1": None}

    all_job_details, _, _ = process_job_logs(
        mock_client, mock_cache, in_details, ["giovanni"], app_logger
    )

    assert isinstance(all_job_details, dict)
    assert all_job_details == in_details


def test_process_job_logs_invalid_state(app_logger):
    mock_client = MagicMock()
    mock_cache = MagicMock()
    in_details = {"1": {"state": "running"}}

    all_job_details, _, _ = process_job_logs(
        mock_client, mock_cache, in_details, ["giovanni"], app_logger
    )

    assert isinstance(all_job_details, dict)
    assert all_job_details == in_details


def test_process_job_logs_done_state_cached_no_parser(app_logger, tmp_path):
    mock_client = MagicMock()
    mock_cache = MagicMock()
    log_file = tmp_path / "pippo.txt"
    with open(log_file, "w") as f:
        f.write("Some interesting line")

    mock_cache.get_cached_log_filepath.return_value = log_file
    in_details = {"1": {"state": "done"}}

    all_job_details, _, _ = process_job_logs(
        mock_client, mock_cache, in_details, [{"log_filename": "something"}], app_logger
    )

    assert isinstance(all_job_details, dict)
    assert all_job_details == in_details


def test_process_job_logs_parsing_failure(app_logger):
    """
    Tests that process_job_logs correctly handles a failure result from
    _parse_log_content without mocking the private function.
    """
    mock_client = MagicMock()
    mock_cache = MagicMock()
    job_id = "1"
    log_filename = "autoinst-log.txt"
    in_details = {job_id: {"id": job_id, "state": "done", "name": "my-test"}}
    parsers_config = [{"log_filename": log_filename, "name": "autoinst-parser"}]
    log_path = "/fake/path/that/does/not/exist"
    mock_cache.get_cached_log_filepath.return_value = log_path

    error_message = f"Log file not found at {log_path}"
    expected_error_log = [{"level": "error", "message": error_message}]

    # Call the function without patching _parse_log_content
    all_job_details, _, server_logs = process_job_logs(
        mock_client, mock_cache, in_details, parsers_config, app_logger
    )

    # Verify that the expected error is in the server logs
    assert any(e == expected_error_log[0] for e in server_logs)

    # Verify the error is correctly reported in the job's log_results
    result_details = all_job_details[job_id]
    assert "log_results" in result_details
    log_result = result_details["log_results"][log_filename]

    assert "error" in log_result
    assert log_result["error"] == error_message
    assert "content" not in log_result

    # Ensure details with the failure are cached to prevent reprocessing
    mock_cache.write_details.assert_called_once_with(
        job_id, result_details, log_files=[log_filename]
    )
