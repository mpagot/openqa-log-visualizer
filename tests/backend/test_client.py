import pytest
from unittest.mock import patch, MagicMock
from app.client import (
    OpenQAClientWrapper,
    OpenQAClientAPIError,
    OpenQAClientLogDownloadError,
)
from openqa_client.exceptions import RequestError
import requests


@pytest.fixture
def mock_openqa_client():
    """Fixture to mock the OpenQA_Client."""
    with patch("app.client.OpenQA_Client") as mock_client_class:
        mock_instance = MagicMock()
        mock_client_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_openqa_client_class():
    """Fixture to mock the OpenQA_Client class to check call counts."""
    with patch("app.client.OpenQA_Client") as mock_client_class:
        mock_instance = MagicMock()
        mock_client_class.return_value = mock_instance
        yield mock_client_class


def test_client_initialization_success(mock_openqa_client, app_logger):
    """Tests successful client initialization and parsing of URL."""
    wrapper = OpenQAClientWrapper("https://openqa.suse.de/tests/123", app_logger)
    assert wrapper.hostname == "openqa.suse.de"
    assert wrapper.job_id == "123"
    # Accessing the client property triggers initialization
    _ = wrapper.client
    # Check that SSL verification is disabled on the mocked instance
    assert mock_openqa_client.session.verify is False


def test_client_lazy_initialization_is_only_done_once(
    mock_openqa_client_class, app_logger
):
    """Tests that the OpenQA_Client is only initialized once on repeated access."""
    wrapper = OpenQAClientWrapper("https://openqa.suse.de/tests/123", app_logger)

    # Access client property multiple times
    _ = wrapper.client
    _ = wrapper.client

    # Assert that the OpenQA_Client constructor was only called once
    mock_openqa_client_class.assert_called_once_with(server="openqa.suse.de")


@pytest.mark.parametrize(
    "url, error_msg",
    [
        ("http://invalid-url", "Could not find job ID in the URL."),
        ("https://no-job-id.com/path", "Could not find job ID in the URL."),
        ("invalid-url-no-scheme", "Invalid URL provided. Could not parse hostname."),
    ],
)
def test_client_initialization_failure(mock_openqa_client, app_logger, url, error_msg):
    """Tests that client initialization fails with invalid URLs."""
    with pytest.raises(ValueError, match=error_msg):
        OpenQAClientWrapper(url, app_logger)


def test_get_job_details_success(mock_openqa_client, app_logger):
    """Tests successful fetching of job details."""
    mock_openqa_client.openqa_request.return_value = {
        "job": {"id": 123, "name": "test_job"}
    }
    wrapper = OpenQAClientWrapper("https://openqa.suse.de/tests/123", app_logger)
    details = wrapper.get_job_details("123")
    assert details["id"] == 123
    mock_openqa_client.openqa_request.assert_called_once_with("GET", "jobs/123")


def test_get_job_details_no_job_key(mock_openqa_client, app_logger):
    """Tests that an error is raised if the 'job' key is missing from the API response."""
    mock_openqa_client.openqa_request.return_value = {"other_key": "some_value"}
    wrapper = OpenQAClientWrapper("https://openqa.suse.de/tests/123", app_logger)
    with pytest.raises(OpenQAClientAPIError, match="Could not find 'job' key"):
        wrapper.get_job_details("123")


def test_get_job_details_api_error(mock_openqa_client, app_logger):
    """Tests handling of API errors when fetching job details."""
    mock_error = RequestError(
        "GET", "https://openqa.suse.de/api/v1/jobs/123", 500, "Internal Server Error"
    )
    mock_openqa_client.openqa_request.side_effect = mock_error
    wrapper = OpenQAClientWrapper("https://openqa.suse.de/tests/123", app_logger)
    with pytest.raises(
        OpenQAClientAPIError,
        match="API Error for job 123: Status 500 - Internal Server Error",
    ):
        wrapper.get_job_details("123")


def test_get_log_content_success(mock_openqa_client, app_logger):
    """Tests successful download of log content."""
    mock_response = MagicMock()
    mock_response.text = "log content"
    mock_response.raise_for_status.return_value = None
    mock_openqa_client.session.get.return_value = mock_response
    wrapper = OpenQAClientWrapper("https://openqa.suse.de/tests/123", app_logger)
    content = wrapper.get_log_content("123", "autoinst-log.txt")
    assert content == "log content"
    mock_openqa_client.session.get.assert_called_once_with(
        "https://openqa.suse.de/tests/123/file/autoinst-log.txt", timeout=30
    )


def test_get_log_content_http_error(mock_openqa_client, app_logger):
    """Tests handling of HTTP errors when downloading logs."""
    mock_openqa_client.session.get.side_effect = requests.exceptions.RequestException(
        "HTTP Error"
    )
    wrapper = OpenQAClientWrapper("https://openqa.suse.de/tests/123", app_logger)
    with pytest.raises(
        OpenQAClientLogDownloadError,
        match="Failed to download log autoinst-log.txt for job 123: HTTP Error",
    ):
        wrapper.get_log_content("123", "autoinst-log.txt")
