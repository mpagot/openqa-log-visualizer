import os
import logging
import json


class openQACache:
    """Handles the file-based caching mechanism for openQA job data and logs.

    This module provides the `openQACache` class, which is responsible
    for storing and retrieving openQA job details and log files to and from
    the backend local filesystem (usually your laptop).
    The primary goal is to speed up analysis by avoiding repeated downloads
    of the same data from the openQA server.

    Architecture and Design
    -----------------------
    The caching system is designed around the `openQACache` class.

    - **Directory Structure:** The cache is organized in a hierarchical structure.
      A main cache directory (configurable by `cache_dir` in `config.yaml`)
      contains subdirectories for each openQA server hostname.
      Inside each hostname directory, cached data for a specific job is stored
      in a JSON file named after the job ID (e.g., `.cache/openqa.suse.de/12345.json`).

    - **Data Format:** Each cache file is a JSON object containing two main keys:
      - `job_details`: A dictionary holding the complete JSON response for a job's
        details from the openQA API.
      - `log_content`: A string containing the full content of the
        `autoinst-log.txt` for that job.

    Workflow
    --------
    The caching logic is integrated into the main application flow in `app/main.py`:

    1.  **Job Discovery (`discover_jobs`):** When discovering related jobs, the
        application first checks if a cache file exists for a given job ID using
        `cache.hit()`. If it does, `cache.get_data()` is called to retrieve the
        `job_details`, and the API call to the openQA server is skipped.

    2.  **Log Processing (`process_job_logs`):** Before attempting to download a
        log file, the application calls `cache.get_log_content()`. If the log is
        found in the cache, the download is skipped.

    3.  **Cache Writing (`_get_log_from_api`):** A cache file is written only after
        job data and its corresponding log file have been successfully downloaded
        from the openQA API. The `cache.write_data()` method is called to save
        both the `job_details` and `log_content` into a single JSON file.

    Configuration and Invalidation
    ------------------------------
    - The cache directory and maximum size are configured in the `config.yaml` file.
    - As only completed jobs are considered, the cache never become
      invalid or obsolete. Job details or log files are not supposed to change
      in the openQA server for such jobs.
    - The cache is persistent and does not have an automatic expiration or TTL
      (Time To Live) mechanism. It can be manually cleared by deleting the cache
      directory.
    - The application provides an `ignore_cache` option in the `/analyze` API
      endpoint to bypass the cache and force a fresh download of all data.
    """

    def __init__(
        self, cache_path: str, hostname: str, max_size: int, logger: logging.Logger
    ) -> None:
        self.cache_path = cache_path
        self.hostname = hostname
        self.cache_host_dir = os.path.join(self.cache_path, self.hostname)
        self.max_size = max_size
        self.logger = logger
        os.makedirs(self.cache_host_dir, exist_ok=True)

    def get_size(self) -> int:
        total = 0
        try:
            for dirpath, _, filenames in os.walk(self.cache_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
        except FileNotFoundError:
            return 0
        return total

    def _file_path(self, job_id) -> str:
        return os.path.join(self.cache_host_dir, f"{job_id}.json")

    def hit(self, job_id) -> bool:
        return os.path.exists(self._file_path(job_id))

    def get_data(self, job_id) -> dict | None:
        try:
            with open(self._file_path(job_id), "r") as f:
                cached_data = json.load(f)
                job_details = cached_data.get("job_details")
                if job_details:
                    job_details["is_cached"] = True
                    return job_details
                else:
                    self.logger.info(
                        f"Missing job_details in cached_data for job {job_id}"
                    )
                    return None
        except (IOError, json.JSONDecodeError) as e:
            self.logger.error(f"Error reading cache for job {job_id}: {e}")
            return None

    def get_log_content(self, job_id: str) -> tuple[str | None, bool]:
        """
        Attempts to retrieve log content for a specific job from the cache.

        Args:
            job_id: The ID of the job.

        Returns:
            A tuple containing the log content (str) and a boolean indicating
            if it was a cache hit. Returns (None, False) on a cache miss or error.
        """
        cache_file = self._file_path(job_id)
        if not os.path.exists(cache_file):
            return None, False

        try:
            with open(cache_file, "r") as f:
                cached_data = json.load(f)
                log_content = cached_data.get("log_content")
                if log_content:
                    self.logger.info(f"Cache hit for log content of job {job_id}.")
                    return log_content, True
                else:
                    self.logger.warning(
                        f"Cache file for job {job_id} exists but contains no 'log_content'."
                    )
                    return None, False
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Failed to read or parse cache file {cache_file}: {e}")
            return None, False

    def write_data(self, job_id: str, job_details: dict, log_content: str) -> None:
        """
        Writes job details and log content to a cache file.

        Args:
            job_id: The ID of the job.
            job_details: A dictionary containing the job's details.
            log_content: A string containing the job's log content.
        """
        cache_file = self._file_path(job_id)
        try:
            with open(cache_file, "w") as f:
                json.dump({"job_details": job_details, "log_content": log_content}, f)
            self.logger.info(f"Successfully cached data for job {job_id}.")
        except (IOError, TypeError) as e:
            self.logger.error(f"Failed to write cache for job {job_id}: {e}")
