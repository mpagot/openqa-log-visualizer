
from flask import Flask, jsonify, render_template, request
from openqa_client.client import OpenQA_Client
from openqa_client.exceptions import RequestError
from urllib.parse import urlparse
import requests
import logging
import re

app = Flask(__name__)

def parse_autoinst_log(log_content: str) -> list:
    """
    Parses the content of an autoinst-log.txt file to extract only the lines
    containing specific keywords related to barriers and mutexes.

    Args:
        log_content: The full string content of the log file.

    Returns:
        A list of dictionaries, where each dictionary represents a relevant
        log line and contains its timestamp and full message.
    """
    parsed_log = []
    log_keywords = [
        "Waiting for barriers creation", "mutex lock", "mutex unlock",
        "Waiting for barrier", "barrier wait", "barrier not released"
    ]
    timestamp_re = re.compile(r'^\[([^\]]+)\]')
    for line in log_content.splitlines():
        if any(keyword in line for keyword in log_keywords):
            match = timestamp_re.match(line)
            if match:
                timestamp = match.group(1)
                message = line[len(match.group(0)) :].strip()
            else:
                timestamp = "unknown"
                message = line.strip()
            parsed_log.append({"timestamp": timestamp, "message": message})
    return parsed_log

def format_job_name(full_name: str) -> str:
    """
    Parses the full job name to extract a more concise name.
    e.g., '...-qam_ha_rolling_update_support_server@64bit' -> 'support_server'
    """
    if not full_name:
        return "Unknown Name"
    # This regex captures the part between 'qam_ha_rolling_update_' and '@64bit'
    match = re.search(r'qam_ha_rolling_update_(.+)@64bit', full_name)
    if match and match[1]:
        extracted_part = match[1]
        if extracted_part == "support_server":
            return "support_server"
        elif extracted_part == "node01":
            return "node1"
        elif extracted_part == "node02":
            return "node2"
    # Fallback to the full name if no specific pattern matches
    return full_name

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    log_url = request.json['log_url']
    job_id = "unknown"
    hostname = None
    debug_log = []
    try:
        app.logger.info(f"Received analysis request for URL: {log_url}")
        parsed_url = urlparse(log_url)
        hostname = parsed_url.hostname
        debug_log.append({"level": "info", "message": f"Parsed hostname: {hostname}"})
        app.logger.info(f"Parsed hostname: {hostname}")

        # Extract job ID from the URL path
        match = re.search(r'/tests/(\d+)', parsed_url.path)
        if not match:
            error_msg = 'Error: Could not find job ID in the URL.'
            debug_log.append({"level": "error", "message": error_msg})
            app.logger.error(error_msg)
            return jsonify({"error": error_msg, "debug_log": debug_log}), 400
        job_id = match.group(1)
        debug_log.append({"level": "info", "message": f"Extracted job ID: {job_id}"})
        app.logger.info(f"Extracted job ID: {job_id}")

        client = OpenQA_Client(server=hostname)
        # The following line disables SSL certificate verification.
        # This is a workaround for the 'CERTIFICATE_VERIFY_FAILED' error,
        # which typically occurs when the server uses a self-signed or
        # internal CA certificate not trusted by your system.
        # WARNING: This is insecure and should NOT be used in production
        # without understanding the risks. A better solution is to provide
        # a path to your CA bundle: client.session.verify = '/path/to/ca.pem'
        client.session.verify = False
        debug_log.append({"level": "error", "message": "WARNING: SSL certificate verification has been disabled. This is insecure."})
        app.logger.warning("SSL certificate verification has been disabled.")

        debug_log.append({"level": "info", "message": f"Initialized OpenQA_Client for server: {hostname}"})
        app.logger.info(f"Initialized OpenQA_Client for server: {hostname}")

        all_job_details = {}
        jobs_to_fetch = [job_id]
        fetched_jobs = set()

        while jobs_to_fetch:
            current_job_id = jobs_to_fetch.pop(0)
            if current_job_id in fetched_jobs:
                continue
            fetched_jobs.add(current_job_id)

            job_url = f"https://{hostname}/t{current_job_id}"

            debug_log.append({"level": "info", "message": f"Fetching details for job {current_job_id} from API..."})
            app.logger.info(f"Fetching details for job {current_job_id} from API...")
            try:
                job_details_response = client.openqa_request('GET', f"jobs/{current_job_id}")
                job_details = job_details_response.get('job')

                if not job_details:
                    error_msg = f"Error: Could not find 'job' key in the API response for ID {current_job_id}."
                    all_job_details[current_job_id] = {"error": error_msg, "job_url": job_url}
                    debug_log.append({"level": "error", "message": error_msg})
                    app.logger.error(f"{error_msg} Raw response: {job_details_response}")
                    continue

                # Add formatted name and job URL to the details
                job_details['short_name'] = format_job_name(job_details.get('name', ''))
                job_details['job_url'] = job_url
                all_job_details[current_job_id] = job_details
                app.logger.debug(f"Full API response for job {current_job_id}: {job_details_response}")

                # Download autoinst-log.txt for the current job
                log_file_url = f"https://{hostname}/tests/{current_job_id}/file/autoinst-log.txt"
                debug_log.append({"level": "info", "message": f"Downloading log for job {current_job_id} from {log_file_url}"})
                app.logger.info(f"Downloading log for job {current_job_id} from {log_file_url}")
                try:
                    # Use the client's session to benefit from existing setup (e.g., verify=False)
                    log_response = client.session.get(log_file_url, timeout=30)
                    log_response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
                    all_job_details[current_job_id]['autoinst-log'] = parse_autoinst_log(log_response.text)
                    debug_log.append({"level": "info", "message": f"Successfully downloaded and parsed log for job {current_job_id}."})
                    app.logger.info(f"Successfully downloaded and parsed log for job {current_job_id}.")
                except requests.exceptions.RequestException as log_e:
                    error_msg = f"Failed to download log for job {current_job_id}: {log_e}"
                    all_job_details[current_job_id]['autoinst-log'] = f"ERROR: {error_msg}"
                    debug_log.append({"level": "error", "message": error_msg})
                    app.logger.error(error_msg)

                parallel_jobs = job_details.get("children", {}).get("Parallel", [])
                if parallel_jobs:
                    debug_log.append({"level": "info", "message": f"Found parallel jobs for {current_job_id}: {parallel_jobs}"})
                    app.logger.info(f"Found parallel jobs for {current_job_id}: {parallel_jobs}")
                    for parallel_id in parallel_jobs:
                        if str(parallel_id) not in fetched_jobs:
                            jobs_to_fetch.append(str(parallel_id))

            except RequestError as e:
                error_message = f"API Error from {hostname} for job {current_job_id}: Status {e.status_code} - {e.text}"
                all_job_details[current_job_id] = {"error": error_message, "job_url": job_url}
                debug_log.append({"level": "error", "message": error_message})
                app.logger.error(error_message)
                continue

        app.logger.info(f"Successfully fetched details for jobs: {list(all_job_details.keys())}")
        return jsonify({"jobs": all_job_details, "debug_log": debug_log})
    except RequestError as e:
        error_message = f"API Error from {hostname} for job {job_id}: Status {e.status_code} - {e.text}"
        debug_log.append({"level": "error", "message": error_message})
        app.logger.error(error_message)
        return jsonify({"error": error_message, "debug_log": debug_log}), e.status_code
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        if hostname:
            error_message = f'Error connecting to {hostname}: {e}'
        debug_log.append({"level": "error", "message": error_message})
        app.logger.exception(error_message)
        return jsonify({"error": error_message, "debug_log": debug_log}), 500

if __name__ == '__main__':
    app.run(debug=True)
