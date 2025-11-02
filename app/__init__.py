import os
import sys
import yaml
import re
import logging
from typing import Any, Dict, List, Optional, Pattern, Tuple


def load_configuration(
    app_logger: logging.Logger,
) -> Tuple[str, int, List[Dict[str, Any]], Pattern[str], Pattern[str], int]:
    """
    Loads configuration from YAML file, pre-compiles regexes, and returns
    key configuration variables.

    Args:
        app_logger: The Flask app's logger for logging errors.

    Returns:
        A tuple containing:
        - CACHE_DIR: The path to the cache directory.
        - CACHE_MAX_SIZE: The max size allowed for the cache folder..
        - file_log_parsers: The list of parser configurations with compiled regexes.
        - timestamp_re: Compiled regex for parsing timestamps.
        - perl_exception_re: Compiled regex for parsing Perl exceptions.
        - max_jobs_to_explore: The maximum number of related jobs to discover.
    """
    # Some dafaults
    CONFIG_FILE = os.environ.get("OQTV_CONFIG_FILE", "config.yaml")
    CACHE_DIR = "./.cache"
    CACHE_MAX_SIZE = None

    # Load configuration from YAML file
    try:
        with open(CONFIG_FILE, "r") as f:
            config = yaml.safe_load(f)
    except (IOError, yaml.YAMLError) as e:
        app_logger.error("Error loading configuration file %s: %s", CONFIG_FILE, e)
        sys.exit(1)

    # The maximum number of related openQA jobs to discover and fetch,
    # starting from the initial URL. Related means parent or child jobs.
    max_jobs_to_explore = config.get("max_jobs_to_explore", 10)

    # Cache configuration
    if config.get("cache"):
        cache_cfg = config.get("cache")
        if isinstance(cache_cfg, dict):
            if "cache_dir" in cache_cfg:
                CACHE_DIR = cache_cfg["cache_dir"]
            if "cache_max_size" in cache_cfg:
                CACHE_MAX_SIZE = int(cache_cfg["cache_max_size"])

    # Pre-compile all regex patterns to catch errors early
    # and improve performance.
    file_log_parsers = []
    if config.get("log_parsers", []):
        file_log_parsers.extend(config.get("log_parsers", []))

    for file_parser in file_log_parsers:
        for k in ["name", "log_filename"]:
            if not file_parser.get(k):
                app_logger.error(
                    "Invalid %s for file_parser:%s is missing '%s'",
                    CONFIG_FILE,
                    file_parser,
                    k)
                sys.exit(1)

        for pattern in file_parser.get("patterns", []):
            for k in ["name", "match_name"]:
                if not pattern.get(k):
                    app_logger.error(
                        "Invalid %s for file_parser:%s pattern %s is missing '%s'",
                        CONFIG_FILE,
                        file_parser,
                        pattern,
                        k,
                    )
                    sys.exit(1)
            try:
                pattern["match_name"] = re.compile(pattern["match_name"])
                if "name" not in pattern["match_name"].groupindex:
                    app_logger.error(
                        "Invalid 'match_name' regular expression '%s' in %s for parser '%s: "
                        "missing named group '(?P<name>...)'. This is required for short job name display.",
                         pattern['match_name'].pattern, CONFIG_FILE, pattern['name'])
                    sys.exit(1)
            except re.error as e:
                app_logger.error(
                    "Invalid 'match_name' regular expression '%s' in %s for parser '%s: %s",
                    pattern['match_name'], CONFIG_FILE, pattern['name'], e)
                sys.exit(1)

            for channel in pattern.get("channels", []):
                for k in ["name", "pattern"]:
                    if not channel.get(k):
                        app_logger.error(
                            f"Invalid configuration in {CONFIG_FILE}: channel '{channel}' is missing its '{k}' field."
                        )
                        sys.exit(1)
                try:
                    channel["pattern"] = re.compile(channel["pattern"])
                except re.error as e:
                    app_logger.error(
                        f"Invalid regular expression '{channel['pattern']}' in {CONFIG_FILE} for parser '{pattern['name']}' channel '{channel['name']}': {e}"
                    )
                    sys.exit(1)

    timestamp_re = re.compile(r"^\[([^\]]+)\]")
    perl_exception_re = re.compile(r" at .*?\.pm line \d+")

    return (
        CACHE_DIR,
        CACHE_MAX_SIZE,
        file_log_parsers,
        timestamp_re,
        perl_exception_re,
        max_jobs_to_explore,
    )
