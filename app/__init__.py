import os
import sys
import yaml
import re
import logging
from typing import Tuple, List, Dict, Any, Pattern


def load_configuration(
    app_logger: logging.Logger,
) -> Tuple[str, List[Dict[str, Any]], Pattern, Pattern]:
    """
    Loads configuration from YAML file, pre-compiles regexes, and returns
    key configuration variables.

    Args:
        app_logger: The Flask app's logger for logging errors.

    Returns:
        A tuple containing:
        - CACHE_DIR: The path to the cache directory.
        - autoinst_log_parsers: The list of parser configurations with compiled regexes.
        - timestamp_re: Compiled regex for parsing timestamps.
        - perl_exception_re: Compiled regex for parsing Perl exceptions.
    """
    CACHE_DIR = "./.cache"

    # Load configuration from YAML file
    CONFIG_FILE = os.environ.get("CONFIG_FILE", "config.yaml")
    try:
        with open(CONFIG_FILE, "r") as f:
            config = yaml.safe_load(f)
    except (IOError, yaml.YAMLError) as e:
        app_logger.error(f"Error loading configuration file {CONFIG_FILE}: {e}")
        sys.exit(1)

    autoinst_log_parsers = config.get("autoinst_parser", [])

    # Pre-compile all regex patterns to catch errors early and improve performance.
    for parser in autoinst_log_parsers:
        match_name_str = parser.get("match_name")
        if match_name_str:
            try:
                parser["match_name"] = re.compile(match_name_str)
            except re.error as e:
                app_logger.error(
                    f"Invalid 'match_name' regular expression in {CONFIG_FILE} for parser '{parser.get('name')}': {e}"
                )
                app_logger.error(f"Pattern: {match_name_str}")
                sys.exit(1)

        for channel in parser.get("channels", []):
            pattern_str = channel.get("pattern")
            if pattern_str:
                try:
                    channel["pattern"] = re.compile(pattern_str)
                except re.error as e:
                    app_logger.error(
                        f"Invalid regular expression in {CONFIG_FILE} for parser '{parser.get('name')}' channel '{channel.get('name')}': {e}"
                    )
                    app_logger.error(f"Pattern: {pattern_str}")
                    sys.exit(1)

    timestamp_re = re.compile(r"^\[([^\]]+)\]")
    perl_exception_re = re.compile(r" at .*?\.pm line \d+")

    return CACHE_DIR, autoinst_log_parsers, timestamp_re, perl_exception_re