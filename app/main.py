
from flask import Flask, jsonify, render_template, request
from openqa_client.client import OpenQA_Client
from openqa_client.exceptions import RequestError
from urllib.parse import urlparse
import requests
import logging
import re
import time
import sys
import json
import os

app = Flask(__name__)

CACHE_DIR = "./.cache"

def parse_autoinst_log(log_content: str) -> list:
    """
    Parses the content of an autoinst-log.txt file to extract only the lines
    containing specific keywords related to barriers and mutexes. It also
    extracts the name of the barrier or mutex if present.

    Args:
        log_content: The full string content of the log file.

    Returns:
        A list of dictionaries, where each dictionary represents a relevant
        log line and contains its timestamp, message, and optionally the
        barrier/mutex name.
    """
    parsed_log = []
    log_patterns = [
        # --- Critical Errors ---
        re.compile(r".*acquiring mutex '(?P<mutex>[^']+)': lock owner already finished"),
        re.compile(r".*barrier '(?P<barrier>[^']+)': timeout after \d+ seconds"),

        # --- State Changes (Paused/Waiting/Polling) ---
        re.compile(r'.*testapi::record_info\(title="Paused(?P<duration>[\s\dms]*)", output="Wait for (?P<lock_name>\S+)'),
        #re.compile(r"mutex lock '(?P<mutex>[^']+)': unavailable, sleeping \d+ seconds"),
        re.compile(r"barrier '(?P<barrier>[^']+)'.*not released.*sleeping.*"),

        # --- Core API Calls ---
        re.compile(r"mutex create '(?P<mutex>[^']+)'"),
        re.compile(r"mutex lock '(?P<mutex>[^']+)'"),
        re.compile(r"mutex unlock '(?P<mutex>[^']+)'"),
        #re.compile(r"barrier create '(?P<barrier>[^']+)': for (?P<tasks>\d+) tasks"),
        re.compile(r"barrier create '(?P<barrier>[^']+)'"),
        re.compile(r"barrier wait '(?P<barrier>[^']+)'"),
        re.compile(r"Waiting for barrier (?P<barrier>\w+)..."),
        re.compile(r"Waiting for barriers creation"),

        # --- Test Module Context ---
        re.compile(r'starting (?P<module>\S+) tests/\S+\.pm'),
        re.compile(r'finished (?P<module>\S+) \S+ \(runtime: \d+ s\)')
    ]
    timestamp_re = re.compile(r'^\[([^\]]+)\]')
    for line in log_content.splitlines():
        for pattern in log_patterns:
            search_match = pattern.search(line)
            if search_match:
                timestamp_match = timestamp_re.match(line)
                if timestamp_match:
                    timestamp = timestamp_match.group(1)
                    message = line[len(timestamp_match.group(0)):].strip()
                else:
                    timestamp = "unknown"
                    message = line.strip()

                log_entry = {"timestamp": timestamp, "message": message}
                group_dict = search_match.groupdict()

                for group_name in ['mutex', 'barrier', 'module']:
                    if group_name in group_dict:
                        log_entry[group_name] = group_dict[group_name]
                parsed_log.append(log_entry)
                break  # Found a match, go to the next line
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
    ignore_cache = request.json.get('ignore_cache', False)
    job_id = "unknown"
    hostname = None
    debug_log = []
    performance_metrics = {
        "api_calls": [],
        "log_downloads": [],
        "log_parsing": [],
        "cache_hits": 0
    }
    try:
        app.logger.info(f"Received analysis request for URL: {log_url}")
        parsed_url = urlparse(log_url)
        hostname = parsed_url.hostname
        debug_log.append({"level": "info", "message": f"Parsed hostname: {hostname}"})
        app.logger.info(f"Parsed hostname: {hostname}")

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
        client.session.verify = False
        debug_log.append({"level": "warning", "message": "SSL certificate verification has been disabled. This is insecure."})
        app.logger.warning("SSL certificate verification has been disabled.")

        all_job_details = {}
        jobs_to_fetch = [job_id]
        fetched_jobs = set()
        max_jobs_to_explore = 10

        discovery_loop_start = time.perf_counter()
        while jobs_to_fetch and len(fetched_jobs) < max_jobs_to_explore:
            current_job_id = jobs_to_fetch.pop(0)
            if current_job_id in fetched_jobs:
                continue
            fetched_jobs.add(current_job_id)

            cache_host_dir = os.path.join(CACHE_DIR, hostname)
            cache_file_path = os.path.join(cache_host_dir, f"{current_job_id}.json")
            job_details = None

            if not ignore_cache and os.path.exists(cache_file_path):
                debug_log.append({"level": "info", "message": f"Cache hit for job {current_job_id}."})
                app.logger.info(f"Cache hit for job {current_job_id}.")
                performance_metrics["cache_hits"] += 1
                with open(cache_file_path, 'r') as f:
                    cached_data = json.load(f)
                    job_details = cached_data.get("job_details")
                    log_content = cached_data.get("log_content")
                    if job_details:
                        job_details['is_cached'] = True
                        if log_content:
                            log_parsing_start = time.perf_counter()
                            job_details['autoinst-log'] = parse_autoinst_log(log_content)
                            log_parsing_end = time.perf_counter()
                            performance_metrics["log_parsing"].append({"job_id": current_job_id, "duration": log_parsing_end - log_parsing_start})

            if not job_details:
                debug_log.append({"level": "info", "message": f"Cache miss for job {current_job_id}. Fetching from API..."})
                try:
                    api_call_start = time.perf_counter()
                    job_details_response = client.openqa_request('GET', f"jobs/{current_job_id}")
                    api_call_end = time.perf_counter()
                    performance_metrics["api_calls"].append({"job_id": current_job_id, "duration": api_call_end - api_call_start})
                    job_details = job_details_response.get('job')

                    if not job_details:
                        all_job_details[current_job_id] = {"error": f"Error: Could not find 'job' key in the API response for ID {current_job_id}."}
                        continue
                    
                    job_details['is_cached'] = False

                    if job_details.get('state') == 'done':
                        log_file_url = f"https://{hostname}/tests/{current_job_id}/file/autoinst-log.txt"
                        log_download_start = time.perf_counter()
                        log_response = client.session.get(log_file_url, timeout=30)
                        log_download_end = time.perf_counter()
                        performance_metrics["log_downloads"].append({"job_id": current_job_id, "duration": log_download_end - log_download_start, "size_bytes": len(log_response.content)})
                        log_response.raise_for_status()
                        log_content = log_response.text
                        
                        log_parsing_start = time.perf_counter()
                        job_details['autoinst-log'] = parse_autoinst_log(log_content)
                        log_parsing_end = time.perf_counter()
                        performance_metrics["log_parsing"].append({"job_id": current_job_id, "duration": log_parsing_end - log_parsing_start})

                        os.makedirs(cache_host_dir, exist_ok=True)
                        with open(cache_file_path, 'w') as f:
                            json.dump({"job_details": job_details, "log_content": log_content}, f)
                        debug_log.append({"level": "info", "message": f"Cached data for job {current_job_id}."})
                    else:
                        job_details['autoinst-log'] = f"INFO: Log not downloaded because job state is '{job_details.get('state')}'."

                except RequestError as e:
                    error_message = f"API Error from {hostname} for job {current_job_id}: Status {e.status_code} - {e.text}"
                    all_job_details[current_job_id] = {"error": error_message}
                    debug_log.append({"level": "error", "message": error_message})
                    continue

            if job_details:
                job_details['short_name'] = format_job_name(job_details.get('name', ''))
                job_details['job_url'] = f"https://{hostname}/t{current_job_id}"
                all_job_details[current_job_id] = job_details

                for relation in ["children", "parents"]:
                    parallel_jobs = job_details.get(relation, {}).get("Parallel", [])
                    if parallel_jobs:
                        for parallel_id in parallel_jobs:
                            if str(parallel_id) not in fetched_jobs:
                                jobs_to_fetch.append(str(parallel_id))

        discovery_loop_end = time.perf_counter()
        performance_metrics["discovery_loop_duration"] = discovery_loop_end - discovery_loop_start

        timeline_creation_start = time.perf_counter()
        timeline_events = []
        for job_id_key, details in all_job_details.items():
            if not details.get('error') and 'autoinst-log' in details:
                log_data = details['autoinst-log']
                if isinstance(log_data, list):
                    for index, log_entry in enumerate(log_data):
                        event_data = log_entry.copy()
                        event_data['job_id'] = job_id_key
                        event_data['log_index'] = index
                        timeline_events.append(event_data)

        if timeline_events:
            timeline_events.sort(key=lambda x: x['timestamp'])
        timeline_creation_end = time.perf_counter()
        performance_metrics["timeline_creation_duration"] = timeline_creation_end - timeline_creation_start

        response_data = {"jobs": all_job_details, "debug_log": debug_log, "timeline_events": timeline_events}
        json_response_data = json.dumps(response_data)
        performance_metrics["response_size_bytes"] = len(json_response_data.encode('utf-8'))

        app.logger.info("--- Performance Metrics ---")
        app.logger.info(json.dumps(performance_metrics, indent=4))
        app.logger.info("---------------------------")

        app.logger.info(f"Successfully fetched details for jobs: {list(all_job_details.keys())}")
        return jsonify(response_data)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        if hostname:
            error_message = f'Error connecting to {hostname}: {e}'
        debug_log.append({"level": "error", "message": error_message})
        app.logger.exception(error_message)
        return jsonify({"error": error_message, "debug_log": debug_log}), 500

if __name__ == '__main__':
    app.run(debug=True)
