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
        parser_def = dict()
        for k in ["name", "match_name"]:
            parser_def[k] = parser.get(k)
            if not parser_def[k]:
                app_logger.error(f"Invalid configuration in {CONFIG_FILE}: parser '{parser}' is missing its '{k}' field.")
                sys.exit(1)


        try:
            parser["match_name"] = re.compile(parser_def["match_name"])
            if "name" not in parser["match_name"].groupindex:
                app_logger.error(
                        f"Invalid 'match_name' regular expression '{parser_def["match_name"]}' in {CONFIG_FILE} for parser '{parser_def["name"]}': "
                        "missing named group '(?P<name>...)'. This is required for short job name display."
                    )
                sys.exit(1)

        except re.error as e:
            app_logger.error(
                    f"Invalid 'match_name' regular expression '{parser_def["match_name"]}' in {CONFIG_FILE} for parser '{parser_def["name"]}': {e}"
                )
            sys.exit(1)

        for channel in parser.get("channels", []):
            channel_def = dict()
            for k in ["name", "pattern"]:
                channel_def[k] = channel.get(k)
                if not channel_def[k]:
                    app_logger.error(f"Invalid configuration in {CONFIG_FILE}: channel '{channel}' is missing its '{k}' field.")
                    sys.exit(1)
            try:
                channel["pattern"] = re.compile(channel_def["pattern"])
            except re.error as e:
                app_logger.error(
                    f"Invalid regular expression '{channel_def["pattern"]}' in {CONFIG_FILE} for parser '{parser_def['name']}' channel '{channel_def['name']}': {e}"
                )

                sys.exit(1)

    timestamp_re = re.compile(r"^\[([^\]]+)\]")
    perl_exception_re = re.compile(r" at .*?\.pm line \d+")

    return CACHE_DIR, autoinst_log_parsers, timestamp_re, perl_exception_re