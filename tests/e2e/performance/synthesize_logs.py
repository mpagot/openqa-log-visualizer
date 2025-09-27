#!/usr/bin/env python3
"""
Log Synthesizer for Performance Testing.

This script generates a suite of synthetic log files based on a set of predefined
"log profiles". It is designed to create consistent and controllable test data
for benchmarking the performance of log parsing and analysis tools.

Usage:
    python tests/e2e/performance/synthesize_logs.py \
        --config /path/to/your/regex_config.yaml \
        --output-dir /path/to/your/output_directory

Inputs:
1.  `--config` (CLI argument): Path to a YAML file containing the regex
    patterns to be used for generating matching log lines. This is the
    configuration file usually a user provide to the backend.
2.  `--output-dir` (CLI argument): The root directory where the generated
    cache structure will be created.
3.  `log_profiles.yaml` (fixed path): A YAML file located in the same
    directory as this script. It defines the different log "profiles"
    to be generated (e.g., long files with sparse matches, short files
    with dense matches).

Output:
For each profile in `log_profiles.yaml`, this script generates a log file at:
<output_dir>/__ginopino__/<job_id>.autoinst-log.txt
"""
import argparse
import yaml
import os
import sys
import random
import string
import re
from datetime import datetime, timedelta, timezone
from xeger import Xeger

def load_log_profiles(script_dir):
    """
    Loads the log profiles from the fixed `log_profiles.yaml` file.

    Args:
        script_dir: The directory where the script is located.

    Returns:
        A dictionary containing the loaded log profiles.
    """
    profiles_path = os.path.join(script_dir, 'log_profiles.yaml')
    try:
        with open(profiles_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: log_profiles.yaml not found at {profiles_path}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing log_profiles.yaml: {e}", file=sys.stderr)
        sys.exit(1)

def load_regex_config(config_path):
    """
    Loads the regex patterns from the provided config file.

    Args:
        config_path: Path to the regex config YAML file.

    Returns:
        A list of regex pattern strings.
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            # Assumes a specific schema from the project's data model
            patterns = [channel['pattern'] for channel in config['autoinst_parser'][0]['channels']]
            return patterns
    except FileNotFoundError:
        print(f"Error: Regex config file not found at {config_path}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, TypeError, IndexError) as e:
        print(f"Error: Invalid format in regex config file {config_path}. Could not find autoinst_parser[0].channels. Error: {e}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing regex config file: {e}", file=sys.stderr)
        sys.exit(1)

def generate_matching_line(pattern):
    """
    Generates a single random string that matches the given regex pattern.

    Args:
        pattern: The regex pattern to match.

    Returns:
        A random string matching the pattern.
    """
    # The limit is a safeguard against potentially catastrophic regex patterns
    # that could lead to excessively long strings.
    x = Xeger(limit=50)
    return x.xeger(pattern)

def generate_noise_line(patterns, length=100):
    """
    Generates a random string that does not match any of the given patterns.

    Args:
        patterns: A list of regex patterns to avoid matching.
        length: The desired length of the noise string.

    Returns:
        A random string that does not match any of the patterns.
    """
    while True:
        # Generate a random line of alphanumeric characters and spaces.
        noise = ''.join(random.choices(string.ascii_letters + string.digits + ' ', k=length))
        # Ensure it doesn't accidentally match any of our real patterns.
        if not any(re.match(p, noise) for p in patterns):
            return noise

def main():
    """
    Main entry point for the script. Parses arguments, loads configs,
    and orchestrates the log generation process for each defined profile.
    """
    parser = argparse.ArgumentParser(
        description="Generate synthetic log files for performance testing.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--config', type=str, required=True, help='Path to the config.yaml file containing regex patterns.')
    parser.add_argument('--output-dir', type=str, required=True, help='The root directory where the generated log folder structure will be created.')
    
    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.realpath(__file__))
    
    log_profiles = load_log_profiles(script_dir)
    regex_patterns = load_regex_config(args.config)

    print("Starting log generation...")

    for profile_name, profile_data in log_profiles.items():
        print(f"\nGenerating profile: {profile_name}...")
        
        job_id = profile_data['job_id']
        lines = profile_data['lines']
        match_ratio = profile_data['match_ratio']

        output_path = os.path.join(args.output_dir, '__ginopino__')
        os.makedirs(output_path, exist_ok=True)
        
        file_path = os.path.join(output_path, f"{job_id}.autoinst-log.txt")
        
        start_time = datetime.now(timezone.utc)

        try:
            with open(file_path, 'w') as f:
                for i in range(lines):
                    # Increment timestamp for each line to simulate a real log
                    current_time = start_time + timedelta(milliseconds=i * 100)
                    timestamp = current_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
                    
                    if random.random() < match_ratio:
                        line_content = generate_matching_line(random.choice(regex_patterns))
                    else:
                        line_content = generate_noise_line(regex_patterns)
                    
                    # Write the line in a format that mimics the real autoinst-log.txt
                    f.write(f"[{timestamp}] [info] [pid:{random.randint(1000, 9999)}] {line_content}\n")
            print(f"Successfully created {file_path}")
        except IOError as e:
            print(f"Error writing to file {file_path}: {e}", file=sys.stderr)
            sys.exit(1)

    print("\nLog generation complete.")


if __name__ == "__main__":
    main()
