from app.cache import openQACache
import json
import pytest
from pathlib import Path


# Fixture for creating a cache instance with a temporary path
@pytest.fixture
def cache_init(tmp_path, app_logger):
    def _func(ignore_cache=False):
        cache_dir = tmp_path / "cache"
        hostname = "test_host"
        return openQACache(
            str(cache_dir),
            hostname,
            1024 * 1024,
            app_logger,
            user_ignore_cache=ignore_cache,
        )

    return _func


# Fixture for creating a cache instance with a temporary path
@pytest.fixture
def cache(cache_init):
    return cache_init()


def test_constructor(cache):
    """
    Verifies that the openQACache constructor correctly initializes its
    attributes and creates the necessary cache directory structure on the
    filesystem.
    """
    cache_host_dir = Path(cache.cache_host_dir)
    assert cache_host_dir.exists()
    assert cache_host_dir.is_dir()


def test_get_size_empty(cache):
    """
    Verifies that `get_size()` returns 0 for a newly created, empty
    cache.
    """
    assert cache.get_size() == 0


def test_get_size_single_file(cache):
    """
    Verifies that `get_size()` correctly reports the size of a single
    file in the cache.
    """
    file_path = Path(cache.cache_host_dir) / "1"
    test_data_1 = "test data"
    file_path.write_text(test_data_1)
    assert cache.get_size() == len(test_data_1)


def test_get_size_multiple_files(cache):
    """
    Verifies that `get_size()` correctly calculates the total size of a
    cache containing multiple files and subdirectories.
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


def test_get_size_ignores_symlinks(cache):
    """
    Verifies that `get_size()` correctly ignores symbolic links when
    calculating the total cache size to prevent double-counting.
    """
    file_path_1 = Path(cache.cache_host_dir) / "1"
    test_data_1 = "test data"
    file_path_1.write_text(test_data_1)
    assert cache.get_size() == len(test_data_1)

    file_path_2 = Path(cache.cache_host_dir) / "2"
    file_path_2.symlink_to(file_path_1)

    assert cache.get_size() == len(test_data_1)


def test_is_details_cached_miss(cache):
    """
    Verifies that `is_details_cached()` returns `False` for a job ID that
    is not in the cache.
    """
    job_id = "123"
    assert not cache.is_details_cached(job_id)


def test_is_details_cached_hit(cache):
    """
    Verifies that `is_details_cached()` returns `True` for a job ID that exists
    in the cache.
    """
    job_id = "123"
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text("data")
    assert cache.is_details_cached(job_id)


def test_is_details_cached_user_ignore(cache_init):
    """
    Verifies that `is_details_cached()` returns `True` for a job ID
    that exists in the cache.
    """
    this_cache = cache_init(ignore_cache=True)
    job_id = "123"
    file_path = Path(this_cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text("data")
    assert not this_cache.is_details_cached(job_id)


def test_get_data_cache_miss_no_file(cache):
    """
    Verifies that `get_job_details()` returns `None` when the cache file for a
    job ID does not exist.
    """
    job_id = "456"

    # test even before to have the cache file
    assert cache.get_job_details(job_id) is None


def test_get_data_cache_miss_empty_file(cache):
    """
    Verifies that `get_job_details()` returns `None` when the cache file for a
    job ID is empty.
    """
    job_id = "456"
    # test with empty file, file is there but empty
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text("")
    assert cache.get_job_details(job_id) is None


def test_get_data_invalid_json(cache):
    """
    Verifies that `get_job_details()` returns `None` when the cache file
    contains invalid JSON.
    """
    job_id = "456"
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text("this is not json")
    assert cache.get_job_details(job_id) is None


def test_get_data_missing_job_details(cache):
    """
    Verifies that `get_job_details()` returns `None` when the cache file is
    valid JSON but lacks the required 'job_details' key.
    """
    job_id = "456"
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"some": "data"}))
    assert cache.get_job_details(job_id) is None


def test_get_data(cache):
    """
    Verifies that `get_job_details()` successfully retrieves and returns job
    details from a valid cache file.
    """
    job_id = "456"
    job_details = {"id": job_id, "name": "test_job"}
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": job_details, "log_content": "log"}))

    retrieved_data = cache.get_job_details(job_id)

    assert retrieved_data["id"] == job_id


def test_get_data_user_ignore(cache_init):
    """
    Verifies that `get_job_details()` return None even if
    details file is there, when user initialize the cache to ignore the cache
    """
    this_cache = cache_init(ignore_cache=True)
    job_id = "456"
    job_details = {"id": job_id, "name": "test_job"}
    file_path = Path(this_cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": job_details, "log_content": "log"}))

    assert this_cache.get_job_details(job_id) is None


def test_get_cached_log_filepath_missing_details(cache):
    """
    Verifies that `get_cached_log_filepath()` returns `None` when the main
    job details metadata file is missing.
    """
    job_id = "456"
    log_dir = Path(cache.cache_host_dir) / job_id
    assert not log_dir.exists()

    actual_path = cache.get_cached_log_filepath(job_id, "something.txt")

    assert actual_path is None


def test_get_cached_log_filepath_invalid(cache):
    """
    Verifies that `get_cached_log_filepath()` returns `None` when the job
    details file exists but does not contain the 'log_files' key.
    """
    job_id = "456"
    job_details = {"id": job_id, "name": "test_job"}
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": job_details}))
    assert file_path.exists()

    actual_path = cache.get_cached_log_filepath(job_id, "something.txt")

    assert actual_path is None


def test_get_cached_log_filepath_missing_file(cache):
    """
    Verifies that `get_cached_log_filepath()` returns `None` when the log is
    not listed in the 'log_files' metadata.
    """
    job_id = "456"
    log_filename = "something.txt"
    job_details = {"id": job_id, "name": "test_job"}
    log_dir = Path(cache.cache_host_dir)
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(json.dumps({"job_details": job_details, "log_files": []}))
    assert file_path.exists()

    actual_path = cache.get_cached_log_filepath(job_id, log_filename)

    assert actual_path is None
    # Check that calling the method
    # also result in folder to be created
    assert log_dir.exists()
    assert log_dir.is_dir()


def test_get_cached_log_filepath(cache):
    """
    Verifies that `get_cached_log_filepath()` returns the correct file path
    when the log is listed in the metadata and the log file exists on
    disk.
    """
    job_id = "456"
    log_filename = "something.txt"
    job_details = {"id": job_id, "name": "test_job"}
    log_dir = Path(cache.cache_host_dir)
    file_path = Path(cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(
        json.dumps({"job_details": job_details, "log_files": [log_filename]})
    )
    log_file_dir = log_dir / job_id
    log_file_dir.mkdir()
    log_file_path = log_file_dir / log_filename
    log_file_path.write_text("Some info")
    assert file_path.exists()

    actual_path = cache.get_cached_log_filepath(job_id, log_filename)

    assert str(log_file_path) == actual_path
    # Check that calling the method
    # also result in folder to be created
    assert log_dir.exists()
    assert log_dir.is_dir()


def test_get_cached_log_filepath_user_ignore(cache_init):
    """
    Verifies that `get_cached_log_filepath()` returns the correct file path
    when the log is listed in the metadata and the log file exists on
    disk.
    """
    this_cache = cache_init(ignore_cache=True)
    job_id = "456"
    log_filename = "something.txt"
    job_details = {"id": job_id, "name": "test_job"}
    log_dir = Path(this_cache.cache_host_dir)
    file_path = Path(this_cache.cache_host_dir) / f"{job_id}.json"
    file_path.write_text(
        json.dumps({"job_details": job_details, "log_files": [log_filename]})
    )
    log_file_dir = log_dir / job_id
    log_file_dir.mkdir()
    log_file_path = log_file_dir / log_filename
    log_file_path.write_text("Some info")
    assert file_path.exists()

    assert this_cache.get_cached_log_filepath(job_id, log_filename) is None


def test_write_details(cache):
    """
    Verifies that `write_details()` correctly creates a job's JSON
    metadata file with the provided job details and list of log files.
    """
    job_id = "101"
    job_details = {"id": job_id, "name": "meta_job"}
    log_files = ["autoinst.txt", "another.log"]
    job_log_dir = Path(cache.cache_host_dir) / job_id
    job_log_dir.mkdir(parents=True, exist_ok=True)

    # Manually create the log files that write_details assumes exist
    for log in log_files:
        log_path = job_log_dir / log
        log_path.write_text(f"content of {log}")

    cache.write_details(job_id, job_details, log_files)

    # Verify the metadata file
    cache_file = Path(cache.cache_host_dir) / f"{job_id}.json"
    assert cache_file.exists()
    with open(cache_file, "r") as f:
        cached_data = json.load(f)
    assert cached_data["job_details"]["id"] == job_id
    assert cached_data["log_files"] == log_files
    assert "log_content" not in cached_data


def test_write_details_no_logs(cache):
    """
    Verifies that `write_details()` functions correctly when a job has
    no associated log files, creating a metadata file with an empty
    'log_files' list.
    """
    job_id = "202"

    cache.write_details(job_id, {"id": job_id, "name": "no_log_job"}, [])

    # Verify the metadata file
    cache_file = Path(cache.cache_host_dir) / f"{job_id}.json"
    assert cache_file.exists()
    with open(cache_file, "r") as f:
        cached_data = json.load(f)
    assert cached_data["job_details"]["id"] == job_id
    assert cached_data["log_files"] == []
