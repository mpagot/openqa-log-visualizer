from flask import Flask, jsonify, render_template, request
from urllib.parse import urlparse
import requests
import re
import time
import json
import os
from . import load_configuration
from .autoinst_parser import parse_autoinst_log
from .client import (
    OpenQAClientWrapper,
    OpenQAClientError,
    OpenQAClientAPIError,
    OpenQAClientLogDownloadError,
)


app = Flask(__name__)

CACHE_DIR, autoinst_log_parsers, timestamp_re, perl_exception_re = load_configuration(
    app.logger
)


def format_job_name(full_name: str) -> str:
    """
    Parses the full job name to extract a more concise name using the 'match_name'
    regex from the configuration.
    Function is designed to take a full job name (e.g., arch:x86_64:support_server)
    and extract a shorter, more readable name (e.g., support_server)
    based on a regular expression defined in the config.yaml file.
    The key is that the regex must contain a named group (?P<name>...)
    to specify which part of the string to extract.

    Args:
        full_name: The full job name to be parsed.

    Returns:
        name
    """
    if not full_name:
        return "Unknown Name"

    for parser in autoinst_log_parsers:
        match_name_re = parser.get("match_name")
        if match_name_re:
            match = match_name_re.search(full_name)
            if match:
                # The regex is expected to have a 'name' group
                short_name = match.groupdict().get("name")
                if short_name:
                    return short_name

    app.logger.warning(
        f"No parser name in the configuration file matches '{full_name}'"
    )
    return full_name


def find_mutex_pairs(timeline_events: list) -> tuple[list, int]:
    """
    Finds pairs of 'mutex_create' and 'mutex_unlock' events for the same mutex name.

    This function uses a stack-based approach to handle potentially nested locks,
    pairing a 'mutex_unlock' with the most recently seen 'mutex_create' for the
    same mutex name.

    Args:
        timeline_events: A list of all timeline event dictionaries.

    Returns:
        A list of dictionaries, each representing a create/unlock pair.
        An integer count of the number of mutex-related events processed.
    """
    mutex_pairs = []
    mutex_event_count = 0
    # Use a dictionary to track open locks for each mutex name
    open_locks = {}

    # Events are already sorted by timestamp from create_timeline_events
    for event in timeline_events:
        mutex_name = event.get("mutex")
        event_name = event.get("event_name")

        if not mutex_name or not event_name:
            continue

        mutex_event_count += 1
        if event_name == "mutex_create":
            if mutex_name not in open_locks:
                open_locks[mutex_name] = []
            # Push the create event onto a stack for this mutex
            open_locks[mutex_name].append(event)

        elif event_name == "mutex_unlock":
            # If there's an open lock for this mutex, pop it and create a pair
            if mutex_name in open_locks and open_locks[mutex_name]:
                create_event = open_locks[mutex_name].pop()
                mutex_pairs.append(
                    {"mutex": mutex_name, "start_event": create_event, "end_event": event}
                )

    return mutex_pairs, mutex_event_count


def create_timeline_events(all_job_details: dict) -> list:
    """
    Creates a sorted list of timeline events from the parsed log data of all jobs.

    Args:
        all_job_details: A dictionary containing the details of all fetched jobs.

    Returns:
        A sorted list of timeline events.
    """
    timeline_events = []
    for job_id_key, details in all_job_details.items():
        if not details.get("error") and "autoinst-log" in details:
            log_data = details["autoinst-log"]
            if isinstance(log_data, list):
                for index, log_entry in enumerate(log_data):
                    # Events without a timestamp (like exceptions) cannot be plotted.
                    if log_entry.get("timestamp") is None:
                        continue
                    event_data = log_entry.copy()
                    event_data["job_id"] = job_id_key
                    event_data["log_index"] = index
                    timeline_events.append(event_data)

    if timeline_events:
        # This sort will now work safely as all items have a timestamp.
        timeline_events.sort(key=lambda x: x["timestamp"])
    return timeline_events


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    log_url = request.json["log_url"]
    ignore_cache = request.json.get("ignore_cache", False)
    job_id = "unknown"
    hostname = None
    debug_log = []
    performance_metrics = {
        "api_calls": [],
        "log_downloads": [],
        "log_parsing": [],
        "cache_hits": 0,
        "mutex_pairing": {},
    }
    try:
        app.logger.info(f"Received analysis request for URL: {log_url}")

        try:
            client = OpenQAClientWrapper(log_url, app.logger)
            hostname = client.hostname
            job_id = client.job_id
        except (ValueError, OpenQAClientError) as e:
            error_msg = f"Error parsing URL: {e}"
            debug_log.append({"level": "error", "message": error_msg})
            app.logger.error(error_msg)
            return jsonify({"error": error_msg, "debug_log": debug_log}), 400

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

            cache_host_dir = os.path.join(CACHE_DIR, client.hostname)
            cache_file_path = os.path.join(cache_host_dir, f"{current_job_id}.json")
            job_details = None

            if not ignore_cache and os.path.exists(cache_file_path):
                debug_log.append(
                    {"level": "info", "message": f"Cache hit for job {current_job_id}."}
                )
                app.logger.info(f"Cache hit for job {current_job_id}.")
                performance_metrics["cache_hits"] += 1
                with open(cache_file_path, "r") as f:
                    cached_data = json.load(f)
                    job_details = cached_data.get("job_details")
                    if job_details:
                        job_details["is_cached"] = True

            if not job_details:
                debug_log.append(
                    {
                        "level": "info",
                        "message": f"Cache miss for job {current_job_id} or ignore_cache:{ignore_cache}. Fetching from openQA...",
                    }
                )
                try:
                    api_call_start = time.perf_counter()
                    job_details = client.get_job_details(current_job_id)
                    api_call_end = time.perf_counter()
                    performance_metrics["api_calls"].append(
                        {"job_id": current_job_id, "duration": api_call_end - api_call_start}
                    )
                except OpenQAClientAPIError as e:
                    error_message = str(e)
                    all_job_details[current_job_id] = {"error": error_message}
                    debug_log.append({"level": "error", "message": error_message})
                    continue

            if job_details:
                job_details["short_name"] = format_job_name(job_details.get("name", ""))
                job_details["job_url"] = client.get_job_url(current_job_id)
                all_job_details[current_job_id] = job_details

                for relation in ["children", "parents"]:
                    parallel_jobs = job_details.get(relation, {}).get("Parallel", [])
                    if parallel_jobs:
                        for parallel_id in parallel_jobs:
                            if str(parallel_id) not in fetched_jobs:
                                jobs_to_fetch.append(str(parallel_id))
        discovery_loop_end = time.perf_counter()
        performance_metrics["discovery_loop_duration"] = (
            discovery_loop_end - discovery_loop_start
        )

        log_processing_start = time.perf_counter()
        for job_id_key, job_details in all_job_details.items():
            if job_details.get("state") == "done":
                log_content = None
                if job_details.get("is_cached"):
                    cache_file_path = os.path.join(
                        os.path.join(CACHE_DIR, hostname), f"{job_id_key}.json"
                    )
                    with open(cache_file_path, "r") as f:
                        cached_data = json.load(f)
                        log_content = cached_data.get("log_content")

                if not log_content:
                    try:
                        log_download_start = time.perf_counter()
                        log_content = client.get_log_content(
                            job_id_key, "autoinst-log.txt"
                        )
                        log_download_end = time.perf_counter()
                        performance_metrics["log_downloads"].append(
                            {
                                "job_id": job_id_key,
                                "duration": log_download_end - log_download_start,
                                "size_bytes": len(log_content.encode("utf-8")),
                            }
                        )
                        # Save the newly downloaded log to cache
                        os.makedirs(os.path.join(CACHE_DIR, hostname), exist_ok=True)
                        with open(
                            os.path.join(CACHE_DIR, hostname, f"{job_id_key}.json"), "w"
                        ) as f:
                            json.dump(
                                {"job_details": job_details, "log_content": log_content}, f
                            )
                        debug_log.append(
                            {"level": "info", "message": f"Cached data for job {job_id_key}."}
                        )
                    except OpenQAClientLogDownloadError as e:
                        error_msg = str(e)
                        job_details["autoinst-log"] = f"ERROR: {error_msg}"
                        debug_log.append({"level": "error", "message": error_msg})

                if log_content:
                    parser_to_use = None
                    for parser in autoinst_log_parsers:
                        match_name_re = parser.get("match_name")
                        if match_name_re and match_name_re.search(
                            job_details.get("name", "")
                        ):
                            parser_to_use = parser
                            app.logger.info(
                                f"Using parser '{parser['name']}' for job '{job_details.get('name', '')}'"
                            )
                            break

                    if parser_to_use:
                        log_parsing_start = time.perf_counter()
                        parsed_log, optional_columns, line_count, match_count = parse_autoinst_log(
                            log_content,
                            parser_to_use["channels"],
                            timestamp_re,
                            perl_exception_re,
                        )
                        job_details["autoinst-log"] = parsed_log
                        job_details["optional_columns"] = optional_columns
                        log_parsing_end = time.perf_counter()
                        performance_metrics["log_parsing"].append(
                            {
                                "job_id": job_id_key,
                                "duration": log_parsing_end - log_parsing_start,
                                "line_count": line_count,
                                "match_count": match_count,
                            }
                        )
                        job_details["parser_name"] = parser_to_use["name"]
                    else:
                        app.logger.info(
                            f"No matching parser found for job '{job_details.get('name', '')}'"
                        )
                        job_details["parser_name"] = "N/A"

            else:
                job_details["autoinst-log"] = (
                    f"INFO: Log not downloaded because job state is '{job_details.get('state')}'."
                )
        log_processing_end = time.perf_counter()
        performance_metrics["log_processing_duration"] = (
            log_processing_end - log_processing_start
        )

        timeline_creation_start = time.perf_counter()
        timeline_events = create_timeline_events(all_job_details)
        timeline_creation_end = time.perf_counter()
        performance_metrics["timeline_creation_duration"] = (
            timeline_creation_end - timeline_creation_start
        )

        # Find mutex pairs for arrow visualization
        mutex_pairing_start = time.perf_counter()
        mutex_pairs, mutex_events_found = find_mutex_pairs(timeline_events)
        mutex_pairing_end = time.perf_counter()
        performance_metrics["mutex_pairing"] = {
            "duration": mutex_pairing_end - mutex_pairing_start,
            "total_events_processed": len(timeline_events),
            "mutex_events_found": mutex_events_found,
            "pairs_created": len(mutex_pairs),
        }

        # Generate a list of unique event types to be used by the frontend for coloring
        all_types = set()
        for parser in autoinst_log_parsers:
            for channel in parser.get("channels", []):
                type_name = channel.get("type")
                if type_name:
                    all_types.add(type_name)
        all_types.add("exception")

        response_data = {
            "jobs": all_job_details,
            "debug_log": debug_log,
            "timeline_events": timeline_events,
            "event_types": sorted(list(all_types)),
            "mutex_pairs": mutex_pairs,
        }
        json_response_data = json.dumps(response_data)
        performance_metrics["response_size_bytes"] = len(
            json_response_data.encode("utf-8")
        )

        app.logger.info("--- Performance Metrics ---")
        app.logger.info(json.dumps(performance_metrics, indent=4))
        app.logger.info("---------------------------")

        app.logger.info(
            f"Successfully fetched details for jobs: {list(all_job_details.keys())}"
        )
        return jsonify(response_data)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        if hostname:
            error_message = f"Error connecting to {hostname}: {e}"
        debug_log.append({"level": "error", "message": error_message})
        app.logger.exception(error_message)
        return jsonify({"error": error_message, "debug_log": debug_log}), 500


if __name__ == "__main__":
    app.run(debug=True)
