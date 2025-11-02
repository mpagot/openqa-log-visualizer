import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

import requests
import requests.exceptions
from openqa_client.client import OpenQA_Client
from openqa_client.exceptions import RequestError

"""Custom exception classes for the application."""


class OpenQAClientError(Exception):
    """Base exception for all OpenQAClientWrapper errors."""

    pass


class OpenQAClientAPIError(OpenQAClientError):
    """Raised for errors during openQA API requests."""

    pass


class OpenQAClientLogDownloadError(OpenQAClientError):
    """Raised for errors during log file downloads."""

    pass


class OpenQAClientWrapper:
    """A wrapper class for the openqa_client to simplify interactions."""

    def __init__(
        self,
        base_url: str,
        app_logger: logging.Logger,
    ) -> None:
        """
        Initializes the client wrapper. It does not create an 
        OpenQA_Client instance. It will be lazly initialized
        the first time it will be used.

        Args:
            base_url: The URL of the openQA job to analyze.
            app_logger: The Flask app\'s logger for logging messages.
        """
        self.app_logger = app_logger

        parsed_url = urlparse(base_url)
        hostname = parsed_url.hostname
        if not hostname:
            raise ValueError(f"Invalid URL {base_url} provided. Could not parse hostname.")
        self.hostname = hostname

        # Extract job_id from the URL path
        match = re.search(r"/tests/(\d+)", parsed_url.path)
        if not match:
            raise ValueError("Could not find job ID in the URL.")
        self.job_id = match.group(1)
        self._client: Optional[OpenQA_Client] = None

    @property
    def client(self) -> OpenQA_Client:
        """
        Lazily initializes and returns the OpenQA_Client instance.
        The actual client is only created on first access, minimizing
        unnecessary connections when results are fully cached.
        """
        self.app_logger.debug(f"_client:{self._client}")
        if self._client is None:
            self.app_logger.info(f"Initializing OpenQA_Client for {self.hostname}")
            client = OpenQA_Client(server=self.hostname)
            # As per existing logic, SSL verification is disabled.
            # This is insecure.
            client.session.verify = False
            self.app_logger.warning(
                "SSL certificate verification disabled for client connecting to %s",
                self.hostname)
            self._client = client
        return self._client

    def get_job_details(self, job_id: str) -> dict[str, Any]:
        """
        Fetches the details for a specific job using GET jobs/1234

        Args:
            job_id: The ID of the job to fetch.

        Returns:
            A dictionary containing the job details.

        Raises:
            OpenQAClientAPIError: If the API request fails or the response
                                is malformed.
        """
        self.app_logger.info("get_job_details(job_id:%s) for %s",
                             job_id, self.hostname)
        try:
            response = self.client.openqa_request("GET", f"jobs/{job_id}")
            job = response.get("job")
            self.app_logger.debug("job:%s", job)
            if not job:
                raise OpenQAClientAPIError(
                    f"Could not find 'job' key in API response for ID {job_id}."
                )
            return job
        except RequestError as e:
            error_message = (
                f"API Error for job {job_id}: Status {e.status_code} - {e.text}"
            )
            self.app_logger.error(error_message)
            raise OpenQAClientAPIError(error_message) from e

    def download_log_to_file(
        self, job_id: str, filename: str, destination_path: str
    ) -> None:
        """
        Downloads a log file and streams it directly to a file.

        Args:
            job_id: The ID of the job.
            filename: The name of the log file to download.
            destination_path: The local path to save the file to.

        Raises:
            OpenQAClientLogDownloadError: If the download fails.
        """
        log_file_url = f"https://{self.hostname}/tests/{job_id}/file/{filename}"
        try:
            with self.client.session.get(log_file_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(destination_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        except requests.exceptions.RequestException as e:
            error_message = f"Failed to download log \'{filename}\' for job {job_id}: {e}"
            self.app_logger.error(error_message)
            raise OpenQAClientLogDownloadError(error_message) from e

    def get_job_url(self, job_id: str) -> str:
        """Constructs the full URL for a given job ID."""
        return f"https://{self.hostname}/t{job_id}"
