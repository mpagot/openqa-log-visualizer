from app.cache import openQACache
import logging
import json
import pytest
from pathlib import Path


# Fixture for creating a logger instance for tests
@pytest.fixture
def logger():
    return logging.getLogger("test_logger")


# Fixture for creating a cache instance with a temporary path
@pytest.fixture
def cache(tmp_path, logger):
    cache_dir = tmp_path / "cache"
    hostname = "test_host"
    return openQACache(str(cache_dir), hostname, 1024 * 1024, logger)


def test_openqacache_constructor(cache):
    """
    Tests that the OpenQACache constructor correctly initializes attributes
    and creates the cache directory.
    """
    cache_host_dir = Path(cache.cache_host_dir)
    assert cache_host_dir.exists()
    assert cache_host_dir.is_dir()


def test_get_size(cache):
    """
    Tests the get_size method for correct cache size calculation.
    """
    # 1. Test empty cache
    assert cache.get_size() == 0

    # 2. Test with a single file
    file_path = Path(cache._file_path("1"))
    test_data_1 = "test data"
    file_path.write_text(test_data_1)
    assert cache.get_size() == len(test_data_1)

    # 3. Test with multiple files and a subdirectory
    file_path_2 = Path(cache._file_path("2"))
    test_data_2 = "more test data"
    file_path_2.write_text(test_data_2)

    sub_dir = Path(cache.cache_host_dir) / "sub"
    sub_dir.mkdir()
    sub_file_path = sub_dir / "3.json"
    nested_data = "nested data"
    sub_file_path.write_text(nested_data)

    expected_size = len(test_data_1) + len(test_data_2) + len(nested_data)
    assert cache.get_size() == expected_size


def test_hit(cache):
    """
    Tests the hit method for correctly identifying cached jobs.
    """
    # 1. Test cache miss
    assert not cache.hit("123")

    # 2. Test cache hit
    file_path = Path(cache._file_path("123"))
    file_path.write_text("data")
    assert cache.hit("123")


def test_get_data(cache):
    """
    Tests the get_data method for retrieving job details from the cache.
    """
    job_id = "456"
    job_details = {"id": job_id, "name": "test_job"}
    file_path = Path(cache._file_path(job_id))

    # 1. Test cache miss
    assert cache.get_data(job_id) is None

    # 2. Test with valid cached data
    file_path.write_text(json.dumps({"job_details": job_details, "log_content": "log"}))
    retrieved_data = cache.get_data(job_id)
    assert retrieved_data["id"] == job_id
    assert retrieved_data["is_cached"] is True

    # 3. Test with missing 'job_details' key
    file_path.write_text(json.dumps({"log_content": "log only"}))
    assert cache.get_data(job_id) is None

    # 4. Test with invalid JSON
    file_path.write_text("this is not json")
    assert cache.get_data(job_id) is None


def test_get_log_content_miss(cache):
    """
    Tests that get_log_content returns (None, False) on a cache miss.
    """
    content, hit = cache.get_log_content("non_existent_job")
    assert content is None
    assert hit is False


def test_get_log_content_hit(cache):
    """
    Tests that get_log_content correctly retrieves content on a cache hit.
    """
    job_id = "789"
    log_content = "This is the log content."
    file_path = Path(cache._file_path(job_id))
    file_path.write_text(json.dumps({"job_details": {}, "log_content": log_content}))

    retrieved_content, hit = cache.get_log_content(job_id)
    assert retrieved_content == log_content
    assert hit is True


def test_get_log_content_missing_key(cache):
    """
    Tests that get_log_content returns (None, False) if 'log_content' key is missing.
    """
    job_id = "789"
    file_path = Path(cache._file_path(job_id))
    file_path.write_text(json.dumps({"job_details": {}}))

    content, hit = cache.get_log_content(job_id)
    assert content is None
    assert hit is False


def test_get_log_content_invalid_json(cache):
    """
    Tests that get_log_content returns (None, False) for a corrupt cache file.
    """
    job_id = "789"
    file_path = Path(cache._file_path(job_id))
    file_path.write_text("this is not valid json")

    content, hit = cache.get_log_content(job_id)
    assert content is None
    assert hit is False
