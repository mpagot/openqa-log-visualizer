import logging
import time
import json
import os
from typing import Any, Dict, List, Tuple

from flask import Flask, jsonify, render_template, request

from . import load_configuration
from . import utils
from .cache import openQACache
from .client import (
    OpenQAClientWrapper,
)

app = Flask(__name__)

(
    CACHE_DIR,
    CACHE_MAX_SIZE,
    file_log_parsers,
    timestamp_re,
    perl_exception_re,
    MAX_JOBS_TO_EXPLORE,
) = load_configuration(app.logger)


def find_event_pairs(
    timeline_events: list, app_logger: logging.Logger
) -> tuple[list, int]:
    """
    Finds pairs of synchronization events (mutexes and barriers) for visualization.

    It identifies three types of pairs:
    1. Mutex 'create' to 'unlock': For visualizing readiness signals.
    2. Mutex 'lock' to 'unlock': For visualizing critical sections.
    3. Barrier 'create' to 'wait': For visualizing multi-job synchronization points.

    The main constraints in the config.yaml are that:
     - each channel must have a name and a valid pattern,
     - the type must be one that the frontend are prepared to handle
       (e.g., mutex, barrier, module).

    This function sits at the end of the chain and is highly dependent
    on the output of parse_autoinst_log.
    It receives the list of timeline events and uses the type and
    event_name fields to identify synchronization events.
    For example, its logic explicitly checks if event_type == "mutex" and
    if event_name == "mutex_lock".
    If the channels in config.yaml are not defined correctly,
    or if parse_autoinst_log fails to tag the events properly,
    find_event_pairs will not be able to find any pairs.

    Args:
        timeline_events: A list of all timeline event dictionaries.
        app_logger: The Flask app's logger for logging messages.

    Returns:
        - A list of all found event pairs.
        - An integer count of the number of synchronization events processed (performance).
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
                app_logger.debug(f"Ignoring mutex: {event}")
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
                app_logger.debug(f"Ignoring barrier: {event}")
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
        if details.get("error"):
            continue

        for log_filename, log_results in details.get("log_results", {}).items():
            if "content" in log_results and isinstance(log_results["content"], list):
                for index, log_entry in enumerate(log_results["content"]):
                    if log_entry.get("timestamp") is None:
                        continue
                    event_data = log_entry.copy()
                    event_data["job_id"] = job_id_key
                    event_data["log_index"] = index
                    event_data["source_log"] = log_filename
                    timeline_events.append(event_data)

    if timeline_events:
        timeline_events.sort(key=lambda x: x["timestamp"])
    return timeline_events


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    log_url = request.json["log_url"]
    ignore_cache = request.json.get("ignore_cache", False)
    app.logger.debug(
        "analyze(url:%s, ignore_cache:%s). Logger level %s::%s",
        log_url,
        ignore_cache,
        app.logger.level,
        logging.getLevelName(app.logger.level),
    )

    hostname = None

    # List of strings that will be included in the replay for the frontend
    # and that the frontend will render in a dedicated box as a list of
    # debug logs for the user.
    ui_debug_log: List[dict] = []
    performance_metrics: dict[str, Any] = {"total_duration": 0}
    try:
        app.logger.debug(f"Create instance of OpenQAClientWrapper for URL: {log_url}")
        request_start_time = time.perf_counter()

        client = OpenQAClientWrapper(log_url, app.logger)
        hostname = client.hostname
        cache = openQACache(
            CACHE_DIR,
            client.hostname,
            CACHE_MAX_SIZE,
            app.logger,
            user_ignore_cache=ignore_cache,
        )

        all_job_details, perf_ret, server_errors = utils.discover_jobs(
            client,
            cache,
            client.job_id,
            MAX_JOBS_TO_EXPLORE,
            app.logger,
        )
        performance_metrics.update(perf_ret)
        ui_debug_log += server_errors

        # Calculate short name for the UI
        for job_id, details in all_job_details.items():
            if "error" in details:
                app.logger.warning("Ignoring result for %s due to error %s", job_id,details["error"])
                continue
            full_name = details.get("name", "")
            details["short_name"] = utils.format_job_name(full_name, file_log_parsers, app.logger)

        # Heavy log processing
        all_job_details, perf_ret, server_errors = utils.process_job_logs(
            client, cache, all_job_details, file_log_parsers, app.logger
        )
        performance_metrics.update(perf_ret)
        ui_debug_log += server_errors

        # Timeline analysis
        timeline_creation_start = time.perf_counter()
        timeline_events = create_timeline_events(all_job_details)
        timeline_creation_end = time.perf_counter()
        performance_metrics["timeline_creation_duration"] = (
            timeline_creation_end - timeline_creation_start
        )

        pairing_start = time.perf_counter()
        all_event_pairs, events_found = find_event_pairs(timeline_events, app.logger)
        pairing_end = time.perf_counter()
        performance_metrics["event_pairing"] = {
            "duration": pairing_end - pairing_start,
            "total_events_processed": len(timeline_events),
            "sync_events_found": events_found,
            "pairs_created": len(all_event_pairs),
        }

        all_types = set()
        for parser in file_log_parsers:
            for pattern in parser.get("patterns", []):
                for channel in pattern.get("channels", []):
                    type_name = channel.get("type")
                    if type_name:
                        all_types.add(type_name)
        all_types.add("exception")

        response_data = {
            "jobs": all_job_details,
            "debug_log": ui_debug_log,
            "timeline_events": timeline_events,
            "event_types": sorted(list(all_types)),
            "event_pairs": all_event_pairs,
            "errors": server_errors,
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
        ui_debug_log.append({"level": "error", "message": error_message})
        app.logger.exception(error_message)
        return jsonify({"error": error_message, "debug_log": ui_debug_log}), 500


if __name__ == "__main__":
    app.run(debug=True)
