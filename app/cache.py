import os
import logging
import json
from typing import Any


class openQACache:
    """Handles the file-based caching mechanism for openQA job data and logs.

    This module provides the `openQACache` class, which is responsible
    for storing and retrieving openQA job details and log files to and from
    the backend local filesystem (usually your laptop).
    The primary goal is to speed up analysis by avoiding repeated downloads
    of the same data from the openQA server.

    Architecture and Design
    -----------------------

    - **Directory Structure:** The cache is organized in a hierarchical structure.
      A main cache directory (configurable by `cache_dir` in `config.yaml`)
      contains subdirectories for each openQA server hostname.
      Inside each hostname directory, cached data for a specific job is stored
      in a JSON file named after the job ID (e.g., `.cache/openqa.suse.de/12345.json`).

    - **Data Format:** Each cache file is a JSON object containing two main keys:
      - `job_details`: A dictionary holding the complete JSON response for a job's
        details from the openQA API.
      - `log_files`: a list of log files downloaded from openQA and stored as
        separated files assiciated to this job_id. Log files are stored in a folder
        named with the value of the job_id, log filename is the one in this list.
      - [DEPRECATED] `log_content`: A string containing the full content of the
        `autoinst-log.txt` for that job.

    - **Data Flow:** the API provided by this class are only responsible to manage
                     openQA job details metadata and log file path.
                     There is no API to write or read any log content.


    Workflow
    --------
    The caching logic is integrated into the main application flow in `app/main.py`:

    1.  **Job Discovery (`discover_jobs`):** When discovering related jobs, the
        application first checks if a cache file exists for a given job ID using
        `cache.is_details_cached()`. If it does, `cache.get_job_details()` is called to retrieve
        the `job_details`, and the API call to the openQA server is skipped.

    2.  **Log Processing (`process_job_logs`):** Before attempting to download a
        log file, the application calls `cache.get_cached_log_filepath('filename.whatever')`.
        If the log is found in the cache, the download is skipped.

    3.  **Cache Writing (`_get_log_from_api`):** A cache file is written only after
        job data and its corresponding log file have been successfully downloaded
        from the openQA API. The `cache.write_data()` method is called to save
        both the `job_details` and `log_content` into a single JSON file.

    Configuration and Invalidation
    ------------------------------
    - The cache directory and maximum size are configured in the `config.yaml` file.
    - As this project only consider and care about  completed jobs, the cache never become
      invalid or obsolete due to changes in the openQA side.
      Job details or log files are not supposed to change in the openQA server for
      a completed jobs.
    - The cache is persistent and does not have an automatic expiration or TTL
      (Time To Live) mechanism. It can be manually cleared by deleting the cache
      directory.
    - The application frontend provides an `ignore_cache` option in the `/analyze` API
      endpoint to bypass the cache and force a fresh download of all data.
      A user_ignore_cache is available in the class constructor. It allows to
      annotate that the cache is there but user ask to ignore data from it.
    """

    def __init__(
        self, cache_path: str,
        hostname: str,
        max_size: int,
        logger: logging.Logger,
        user_ignore_cache: bool = False
    ) -> None:
        """
        Initializes the cache handler.

        Args:
            cache_path: The root directory where cache files are stored.
            hostname: The hostname of the openQA server, used to create a
                      dedicated subdirectory within the cache_path.
            max_size: The maximum size for the cache. Note: This is not
                      currently enforced by the cache eviction logic.
            logger: The application's logger instance for logging messages.
            used_ignore_cache: The user requested to ignore values from the cache
        """
        self.cache_path = cache_path
        self.hostname = hostname
        self.cache_host_dir = os.path.join(self.cache_path, self.hostname)
        self.max_size = max_size
        self.logger = logger
        self.user_ignore_cache = user_ignore_cache

        os.makedirs(self.cache_host_dir, exist_ok=True)

    def get_size(self) -> int:
        """
        Calculates and returns the total size of the entire cache directory.

        This method walks through all files in the cache path and sums up
        their sizes to determine the total disk space used by the cache.

        Returns:
            The total size of the cache in bytes. Returns 0 if the cache
            directory does not exist.
        """
        # TBD add time performance recording
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

    def _file_path(self, job_id: str) -> str:
        """
        Constructs the full path for a job's details metadata JSON file.

        Args:
            job_id: The ID of the job.

        Returns:
            The absolute path to the cache JSON file for the given job ID.
        """
        return os.path.join(self.cache_host_dir, f"{job_id}.json")

    def is_details_cached(self, job_id: str) -> bool:
        """
        Checks if the cache metadata file exists for a given job ID.

        This method performs a quick check for the presence of the job's
        main JSON metadata file (e.g., '12345.json'). It does NOT validate
        the file's content or guarantee that any associated log files are present.

        Args:
            job_id: The ID of the job to check.

        Returns:
            True if the job's metadata cache file exists, False otherwise.
            Always returns False if 'user_ignore_cache' is enabled.
        """
        if self.user_ignore_cache:
            return False
        return os.path.exists(self._file_path(job_id))

    def get_job_details(self, job_id: str) -> dict[str, Any] | None:
        """
        Retrieves cached job details for a specific job ID.
        Intentionally using same method name of the one in client module.

        Args:
            job_id: The ID of the job whose details are to be retrieved.

        Returns:
            A dictionary containing the job details if the cache is hit and
            the file is valid. Returns None if the file does not exist, is
            corrupt, or is missing the 'job_details' key.
        """
        if self.user_ignore_cache:
            return None
        try:
            with open(self._file_path(job_id), "r") as f:
                cached_data = json.load(f)
                job_details: dict[str, Any] | None = cached_data.get("job_details")
                if job_details:
                    return job_details
                else:
                    self.logger.info(
                        f"Missing job_details in cached_data for job {job_id}"
                    )
                    return None
        except (IOError, json.JSONDecodeError) as e:
            self.logger.error(f"Error reading cache for job {job_id}: {e}")
            return None

    def compose_log_path(self, job_id: str, log_filename: str) -> str:
        """Composes the destination file path for a cached log and ensures its parent directory exists.

        This method acts as a deterministic path builder. It generates the expected
        absolute path for a given log file within the cache structure for a specific job.
        As a side effect, it creates the job-specific log directory if it doesn't already exist.

        Note: This function does not check if the log file itself exists.

        Args:
            job_id: The ID of the job.
            log_filename: The name of the log file (e.g., 'autoinst-log.txt').

        Returns:
            The absolute file path for where the log file should be stored in the cache.
        """
        job_log_dir = os.path.join(self.cache_host_dir, job_id)
        os.makedirs(job_log_dir, exist_ok=True)
        return os.path.join(job_log_dir, log_filename)

    def get_cached_log_filepath(
        self, job_id: str, log_file: str | None = None
    ) -> str | None:
        """
        Retrieves the full filesystem path for a specific cached log file.

        This method verifies a cache hit by performing a multi-step check:
        1.  Ensuring the job's main metadata file exists.
        2.  Reading the metadata and confirming the requested 'log_file' is listed.
        3.  Verifying the actual log file exists on the filesystem at its expected location.

        It returns None if any of these steps fail, signaling a cache miss
        for the specific log file.

        Args:
            job_id: The ID of the job.
            log_file: The filename of the log to retrieve (e.g., 'autoinst-log.txt').

        Returns:
            The absolute local filepath to the cached log file if found.
            None on a cache miss, if the file is missing on disk, or if an
            error occurs during file processing.
        """
        if not log_file or not self.is_details_cached(job_id):
            self.logger.warning(
                "Cache details metadata file for log '%s' of job %s is missing",
                log_file, job_id)
            return None

        details_file = self._file_path(job_id)

        try:
            with open(details_file, "r") as f:
                cached_data = json.load(f)

            # Check for new 'log_files' format
            if "log_files" in cached_data and log_file in cached_data["log_files"]:
                log_path = self.compose_log_path(job_id, log_file)
                if os.path.exists(log_path):
                    self.logger.info(
                        "Cache hit for log file '%s' of job %s",
                        log_file, job_id)
                    return log_path
                else:
                    self.logger.warning(
                        "Details for '%s' of job %s exists, but file is missing",
                        log_file, job_id)
                    # Fall through to return a cache miss

            # Handle deprecated 'log_content' by treating it as
            # a miss to force migration
            if "log_content" in cached_data:
                self.logger.warning(
                    f"Found deprecated 'log_content' for job {job_id}. "
                    "Treating as cache miss to force migration to new format."
                )

            return None
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(
                              "Failed to read or parse cache file %s: %s}",
                              details_file, e)
            return None

    def write_details(
        self, job_id: str, job_details: dict[str, Any], log_files: list[str]
    ) -> None:
        """
        Writes job details and a list of log files to a cache metadata file.

        Args:
            job_id: The ID of the job.
            job_details: A dictionary containing the job's details.
            log_files: A list of log filenames associated with the job.
        """
        cache_file = self._file_path(job_id)
        data_to_cache: dict[str, Any] = {
            "job_details": job_details,
            "log_files": log_files,
        }

        try:
            with open(cache_file, "w") as f:
                json.dump(data_to_cache, f)
            self.logger.info(f"Successfully cached metadata for job {job_id}.")
        except (IOError, TypeError) as e:
            self.logger.error(f"Failed to write cache for job {job_id}: {e}")
