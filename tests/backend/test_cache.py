from app.cache import openQACache
import logging
import json
import pytest
from pathlib import Path


# Fixture for creating a logger instance for tests
# Constructor is calle din the fixture. Is it a good idea?
@pytest.fixture
def logger():
    return logging.getLogger("test_cache logger")


# Fixture for creating a cache instance with a temporary path
@pytest.fixture
def cache(tmp_path, logger):
    cache_dir = tmp_path / "cache"
    hostname = "test_host"
    return openQACache(str(cache_dir), hostname, 1024 * 1024, logger)


def test_constructor(cache):
    """
    Tests that the OpenQACache constructor correctly initializes attributes
    and creates the cache directory.
    """
    cache_host_dir = Path(cache.cache_host_dir)
    assert cache_host_dir.exists()
    assert cache_host_dir.is_dir()


def test_get_size_empty(cache):
    """
    Tests the get_size method for correct cache size calculation.
    Give zero on an empty cache.
    """
    assert cache.get_size() == 0


def test_get_size_single_file(cache):
    """
    Tests the get_size method for correct cache size calculation.
    Test it with a single file, the size has to be just the size
    of that single file.
    """
    file_path = Path(cache.cache_host_dir) / "1"
    test_data_1 = "test data"
    file_path.write_text(test_data_1)
    assert cache.get_size() == len(test_data_1)


def test_get_size_multiple_files(cache):
    """
    Tests the get_size method for correct cache size calculation.
    Test it with a cache populated by many files,
    the size has to be the sum of all of them.
    """
    # this part duplicate previous test, but I like to see if
    # the get_size can also keep track of cache size that grow over the time
    file_path = Path(cache.cache_host_dir) / "1"
    test_data_1 = "test data"
    file_path.write_text(test_data_1)
    assert cache.get_size() == len(test_data_1)

    file_path_2 = Path(cache.cache_host_dir) / "2"
    test_data_2 = "more test data"
    file_path_2.write_text(test_data_2)

    for i in range(4):
        sub_dir = Path(cache.cache_host_dir) / f"sub{i}"
        sub_dir.mkdir()
        sub_file_path = sub_dir / f"{i}.json"
        nested_data = "nested data"
        sub_file_path.write_text(nested_data)

    expected_size = len(test_data_1) + len(test_data_2) + 4 * len(nested_data)
    assert cache.get_size() == expected_size


def test_hit_miss(cache):
    """
    Tests the hit method for correctly identifying cached jobs.
    Test cache miss
    """
    job_id = "123"
    assert not cache.hit(job_id)


def test_hit_hit(cache):
    """
    Tests the hit method for correctly identifying cached jobs.
    Test cache hit
    """
    job_id = "123"
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text("data")
    assert cache.hit(job_id)


def test_get_data_cache_miss_no_file(cache):
    """
    Tests the get_data method for retrieving job details from the cache.
    Test how it behaves in case of missing file.
    """
    job_id = "456"

    # test even before to have the cache file
    assert cache.get_data(job_id) is None


def test_get_data_cache_miss_empty_file(cache):
    """
    Tests the get_data method for retrieving job details from the cache.
    Test how it behaves in case of empty file.
    """
    job_id = "456"
    # test with empty file, file is there but empty
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text("")
    assert cache.get_data(job_id) is None


def test_get_data_invalid_json(cache):
    """
    Tests the get_data method for retrieving job details from the cache.
    Test with invalid cached data
    """
    job_id = "456"
    job_details = {"id": job_id, "name": "test_job"}
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text("this is not json")
    assert cache.get_data(job_id) is None


def test_get_data_missing_job_details(cache):
    """
    Tests the get_data method for retrieving job details from the cache.
    Test with valid cached data, it is json but it miss some mandatory keys
    """
    job_id = "456"
    job_details = {"id": job_id, "name": "test_job"}
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"log_content": "log only"}))
    assert cache.get_data(job_id) is None


def test_get_data(cache):
    """
    Tests the get_data method for retrieving job details from the cache.
    Test with valid cached data
    """
    job_id = "456"
    job_details = {"id": job_id, "name": "test_job"}
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": job_details, "log_content": "log"}))

    retrieved_data = cache.get_data(job_id)
    assert retrieved_data["id"] == job_id
    assert retrieved_data["is_cached"] is True


def test_get_log_content_miss(cache):
    """
    Tests that get_log_content returns (None, False) on a cache miss.
    """
    content, hit = cache.get_log_content("non_existent_job")
    assert content is None
    assert hit is False


def test_get_log_content_invalid_json(cache):
    """
    Tests that get_log_content returns (None, False) for a corrupt cache file.
    """
    job_id = "789"
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text("this is not valid json")

    content, hit = cache.get_log_content(job_id)
    assert content is None
    assert hit is False


def test_get_log_content_missing_key(cache):
    """
    Tests that get_log_content returns (None, False)
    if 'log_content' key is missing.
    """
    job_id = "789"
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": {}}))

    content, hit = cache.get_log_content(job_id)
    assert content is None
    assert hit is False


def test_get_log_content_hit(cache):
    """
    Tests that get_log_content correctly retrieves content on a cache hit.
    Old format using log_content
    """
    job_id = "789"
    log_content = "This is the log content."
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": {}, "log_content": log_content}))

    retrieved_content, hit = cache.get_log_content(job_id)
    assert retrieved_content == log_content
    assert hit is True


def test_get_log_content_hit_file(cache):
    """
    Tests that get_log_content correctly retrieves content on a cache hit.
    New format support multiple log files, and files are not embedded in the json.
    """
    job_id = "789"
    log_content = "This is the log content."
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": {}, "log_files": ["autoinst.txt"]}))
    log_path = Path(cache.cache_host_dir) / job_id / "autoinst.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log_content)

    retrieved_content, hit = cache.get_log_content(job_id, "autoinst.txt")
    assert retrieved_content == log_content
    assert hit is True


def test_get_log_content_log_file_missing(cache):
    """
    Tests that get_log_content correctly retrieves content on a cache hit.
    New format support multiple log files, but the log file
    indicated in the details json  is missing on the disk
    """
    job_id = "789"
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": {}, "log_files": ["autoinst.txt"]}))

    retrieved_content, hit = cache.get_log_content(job_id, "autoinst.txt")
    assert retrieved_content is None
    assert hit is False


def test_write_metadata(cache):
    """
    Tests that write_metadata correctly writes the metadata file.
    """
    job_id = "101"
    job_details = {"id": job_id, "name": "meta_job"}
    log_files = ["autoinst.txt", "another.log"]
    job_log_dir = Path(cache.cache_host_dir) / job_id
    job_log_dir.mkdir(parents=True, exist_ok=True)

    # Manually create the log files that write_metadata assumes exist
    for log in log_files:
        log_path = job_log_dir / log
        log_path.write_text(f"content of {log}")

    cache.write_metadata(job_id, job_details, log_files)

    # Verify the metadata file
    cache_file = Path(cache.cache_host_dir) / f"{job_id}.json"
    assert cache_file.exists()
    with open(cache_file, "r") as f:
        cached_data = json.load(f)
    assert cached_data["job_details"]["id"] == job_id
    assert cached_data["log_files"] == log_files
    assert "log_content" not in cached_data


def test_write_metadata_no_logs(cache):
    """
    Tests that write_metadata correctly handles a job with no log files.
    """
    job_id = "202"

    cache.write_metadata(job_id, {"id": job_id, "name": "no_log_job"}, [])

    # Verify the metadata file
    cache_file = Path(cache.cache_host_dir) / f"{job_id}.json"
    assert cache_file.exists()
    with open(cache_file, "r") as f:
        cached_data = json.load(f)
    assert cached_data["job_details"]["id"] == job_id
    assert cached_data["log_files"] == []


def test_get_log_path(cache):
    """
    Tests that get_log_path returns the correct path for a log file.
    """
    job_id = "456"
    log_filename = "autoinst-log.txt"
    log_dir = Path(cache.cache_host_dir) / job_id
    expected_path = log_dir / log_filename
    assert not log_dir.exists()

    # This method doesn't exist yet, so this will fail
    actual_path = cache.get_log_path(job_id, log_filename)

    assert str(expected_path) == actual_path
    assert log_dir.exists()
    assert log_dir.is_dir()
