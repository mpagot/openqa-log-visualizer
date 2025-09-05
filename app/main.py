from flask import Flask, jsonify, render_template, request
from urllib.parse import urlparse

import logging
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



(
    CACHE_DIR, CACHE_MAX_SIZE,
    autoinst_log_parsers,
    timestamp_re,
    perl_exception_re,
    MAX_JOBS_TO_EXPLORE,
) = load_configuration(app.logger)


def get_dir_size(path='.'):
    """Calculates the total size of a directory in bytes."""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_dir_size(entry.path)
    except FileNotFoundError:
        return 0 # Directory does not exist yet
    return total

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


def find_event_pairs(timeline_events: list, app_logger) -> tuple[list, int]:
    """
    Finds pairs of synchronization events (mutexes and barriers) for visualization.

    It identifies three types of pairs:
    1. Mutex 'create' to 'unlock': For visualizing readiness signals.
    2. Mutex 'lock' to 'unlock': For visualizing critical sections.
    3. Barrier 'create' to 'wait': For visualizing multi-job synchronization points.

    Args:
        timeline_events: A list of all timeline event dictionaries.
        app_logger: The Flask app's logger for logging messages.

    Returns:
        - A list of all found event pairs.
        - An integer count of the number of synchronization events processed.
    """
    all_pairs = []
    event_count = 0

    # Use a dictionary to track the last seen 'create' event for each mutex name
    last_mutex_create_event = {}
    # Use a dictionary of stacks to track open locks for each mutex name
    open_locks: dict[str, list] = {}
    # Use a dictionary to track the last seen 'create' event for each barrier name
    last_barrier_create_event = {}

    # Events are already sorted by timestamp from create_timeline_events
    for event in timeline_events:
        event_type = event.get("type")
        event_name = event.get("event_name")

        if event_type == "mutex":
            mutex_name = event.get("mutex")
            if not mutex_name:
                app_logger.debug(
                    f"Ignoring mutex: {event}"
                )
                continue
            event_count += 1

            if event_name == "mutex_create":
                last_mutex_create_event[mutex_name] = event
            elif event_name == "mutex_lock":
                if mutex_name not in open_locks:
                    open_locks[mutex_name] = []
                open_locks[mutex_name].append(event)
            elif event_name == "mutex_unlock":
                # Pair with last 'create' event for readiness signal
                if mutex_name in last_mutex_create_event:
                    create_event = last_mutex_create_event[mutex_name]
                    all_pairs.append(
                        {
                            "mutex": mutex_name,
                            "start_event": create_event,
                            "end_event": event,
                            "pair_type": "mutex_create_unlock",
                        }
                    )
                # Pair with last 'lock' event for critical section
                if mutex_name in open_locks and open_locks[mutex_name]:
                    lock_event = open_locks[mutex_name].pop()
                    all_pairs.append(
                        {
                            "mutex": mutex_name,
                            "start_event": lock_event,
                            "end_event": event,
                            "pair_type": "mutex_lock_unlock",
                        }
                    )

        elif event_type == "barrier":
            barrier_name = event.get("barrier")
            if not barrier_name:
                app_logger.debug(
                    f"Ignoring barrier: {event}"
                )
                continue
            event_count += 1

            if event_name == "barrier_create":
                last_barrier_create_event[barrier_name] = event
            elif event_name == "barrier_wait":
                if barrier_name in last_barrier_create_event:
                    create_event = last_barrier_create_event[barrier_name]
                    all_pairs.append(
                        {
                            "barrier": barrier_name,
                            "start_event": create_event,
                            "end_event": event,
                            "pair_type": "barrier_create_wait",
                        }
                    )
        else:
            continue

    return all_pairs, event_count


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


def _discover_jobs(client, initial_job_id, ignore_cache, debug_log, max_jobs):
    """Discover all related jobs starting from an initial job ID."""
    all_job_details = {}
    jobs_to_fetch = [initial_job_id]
    fetched_jobs = set()
    performance_metrics = {"api_calls": [], "cache_hits": 0}

    cache_size_start_time = time.perf_counter()
    try:
        cache_size_bytes = get_dir_size(CACHE_DIR)
        app.logger.info(f"Initial cache size: {cache_size_bytes / 1024 / 1024:.2f} MB")
    except Exception as e:
        app.logger.error(f"Failed to calculate cache size: {e}")
        cache_size_bytes = -1
    cache_size_duration = time.perf_counter() - cache_size_start_time
    performance_metrics['cache_size_calc_duration'] = cache_size_duration
    performance_metrics['initial_cache_size_bytes'] = cache_size_bytes

    cache_host_dir = os.path.join(CACHE_DIR, client.hostname)

    discovery_loop_start = time.perf_counter()
    while jobs_to_fetch and len(fetched_jobs) < max_jobs:
        current_job_id = jobs_to_fetch.pop(0)
        if current_job_id in fetched_jobs:
            app.logger.debug(f"Skipping already fetched job {current_job_id}.")
            continue
        fetched_jobs.add(current_job_id)
    
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
                else:
                    app.logger.info("Missing job_details in cached_data:{cached_data}")
        else:
            app.logger.info(f"Cache miss for job {current_job_id} cache_file_path:{cache_file_path} and ignore_cache:{ignore_cache}.")


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
    return all_job_details, performance_metrics


def _process_job_logs(client, all_job_details, debug_log):
    """Fetch and parse logs for all discovered jobs."""
    performance_metrics = {"log_downloads": [], "log_parsing": [], "cache_hits": 0}
    log_processing_start = time.perf_counter()

    for job_id_key, job_details in all_job_details.items():
        if job_details.get("state") != "done":
            job_details["autoinst-log"] = (
                f"INFO: Log not downloaded because job state is '{job_details.get('state')}'."
            )
            continue

        log_content, was_cached = _get_log_from_cache(client.hostname, job_id_key)
        if was_cached:
            performance_metrics["cache_hits"] += 1

        if not log_content:
            log_content, perf = _get_log_from_api(client, job_id_key, job_details, debug_log)
            if perf:
                performance_metrics["log_downloads"].append(perf)

        if log_content:
            _parse_log_content(job_details, log_content, job_id_key, performance_metrics)
        else:
            # This case is hit if log download failed and error was already logged.
            pass

    log_processing_end = time.perf_counter()
    performance_metrics["log_processing_duration"] = (
        log_processing_end - log_processing_start
    )
    return all_job_details, performance_metrics


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    # This is a great place to test the logger's level.
    # This message should appear in the console when running with '--debug'.
    app.logger.debug(
        f"analyze() route handler started. Logger level is {app.logger.level}::{logging.getLevelName(app.logger.level)}."
    )
    log_url = request.json["log_url"]
    ignore_cache = request.json.get("ignore_cache", False)
    job_id = "unknown"
    hostname = None
    debug_log = []
    performance_metrics = {
        "total_duration": 0,
        "cache_hits": 0
    }
    try:
        request_start_time = time.perf_counter()
        app.logger.info(f"Received analysis request for URL: {log_url}")

        try:
            app.logger.debug(f"Create instance of OpenQAClientWrapper for URL: {log_url}")
            client = OpenQAClientWrapper(log_url, app.logger)
            hostname = client.hostname
            job_id = client.job_id
        except (ValueError, OpenQAClientError) as e:
            error_msg = f"Error parsing URL: {e}"
            debug_log.append({"level": "error", "message": error_msg})
            app.logger.error(error_msg)
            return jsonify({"error": error_msg, "debug_log": debug_log}), 400

        # 1. Discover all related jobs
        all_job_details, perf_discovery = _discover_jobs(
            client, job_id, ignore_cache, debug_log, MAX_JOBS_TO_EXPLORE
        )
        performance_metrics.update(perf_discovery)

        # 2. Process logs for all discovered jobs
        all_job_details, perf_logs = _process_job_logs(
            client, all_job_details, debug_log
        )
        # Manually aggregate cache_hits from the two separate counters
        performance_metrics["cache_hits"] += perf_logs.pop("cache_hits", 0)
        performance_metrics.update(perf_logs)

        # 3. Build final response data from processed jobs
        timeline_creation_start = time.perf_counter()
        timeline_events = create_timeline_events(all_job_details)
        timeline_creation_end = time.perf_counter()
        performance_metrics["timeline_creation_duration"] = (
            timeline_creation_end - timeline_creation_start
        )

        # Find event pairs for arrow visualization
        pairing_start = time.perf_counter()
        all_event_pairs, events_found = find_event_pairs(timeline_events, app.logger)
        pairing_end = time.perf_counter()
        performance_metrics["event_pairing"] = {
            "duration": pairing_end - pairing_start,
            "total_events_processed": len(timeline_events),
            "sync_events_found": events_found,
            "pairs_created": len(all_event_pairs),
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
            "event_pairs": all_event_pairs,
        }
        json_response_data = json.dumps(response_data)
        performance_metrics["response_size_bytes"] = len(
            json_response_data.encode("utf-8")
        )

        request_end_time = time.perf_counter()
        performance_metrics["total_duration"] = request_end_time - request_start_time

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


def _get_log_from_cache(hostname, job_id_key):
    """Attempt to retrieve log content from the cache."""
    cache_file_path = os.path.join(os.path.join(CACHE_DIR, hostname), f"{job_id_key}.json")
    if os.path.exists(cache_file_path):
        with open(cache_file_path, "r") as f:
            cached_data = json.load(f)
            log_content = cached_data.get("log_content")
            if log_content:
                return log_content, True  # Return content and cache hit status
    return None, False  # Return no content and no cache hit


def _get_log_from_api(client, job_id_key, job_details, debug_log):
    """Download log content from the API and cache it."""
    try:
        log_download_start = time.perf_counter()
        log_content = client.get_log_content(job_id_key, "autoinst-log.txt")
        log_download_end = time.perf_counter()
        perf = {
            "job_id": job_id_key,
            "duration": log_download_end - log_download_start,
            "size_bytes": len(log_content.encode("utf-8")),
        }

        # Save the newly downloaded log to cache
        os.makedirs(os.path.join(CACHE_DIR, client.hostname), exist_ok=True)
        with open(
            os.path.join(CACHE_DIR, client.hostname, f"{job_id_key}.json"), "w"
        ) as f:
            json.dump({"job_details": job_details, "log_content": log_content}, f)
        debug_log.append(
            {"level": "info", "message": f"Cached data for job {job_id_key}."}
        )
        return log_content, perf
    except OpenQAClientLogDownloadError as e:
        error_msg = str(e)
        job_details["autoinst-log"] = f"ERROR: {error_msg}"
        debug_log.append({"level": "error", "message": error_msg})
        return None, None


def _parse_log_content(job_details, log_content, job_id_key, performance_metrics):
    """Parse the log content using the appropriate parser from the config."""
    parser_to_use = None
    for parser in autoinst_log_parsers:
        match_name_re = parser.get("match_name")
        if match_name_re and match_name_re.search(job_details.get("name", "")):
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
        app.logger.info(f"No matching parser found for job '{job_details.get('name', '')}'")
        job_details["parser_name"] = "N/A"


if __name__ == "__main__":
    app.run(debug=True)
