from datetime import datetime, timedelta
from typing import Any, Dict, List, Pattern, Tuple


def _create_exception_timestamp(timestamp_str: str | None) -> str | None:
    """
    Takes the last known timestamp, adds a small offset, and returns a new
    timestamp string. This is used to give a chronological position to
    multi-line exceptions that don't have their own timestamp.

    Returns None if the input timestamp is invalid or missing.
    """
    if not timestamp_str:
        return None

    # Create a timezone-aware datetime object from the last known timestamp
    dt_object = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    # Add a small offset so it appears just after the last event on the timeline
    new_dt_object = dt_object + timedelta(milliseconds=1)
    # Format back to the original ISO 8601 format with 'Z'
    return new_dt_object.isoformat().replace("+00:00", "Z")


def parse_autoinst_log(
    log_content: str,
    patterns: List[Dict[str, Any]],
    timestamp_re: Pattern,
    perl_exception_re: Pattern,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parses the content of an autoinst-log.txt file to extract only the lines
    containing specific keywords. It also extracts any named groups from the regex
    and captures multi-line Perl exceptions.

    Args:
        log_content: The full string content of the log file.
        patterns: A list of channel objects from the config file,
                  with pre-compiled regex patterns.
        timestamp_re: Compiled regex for parsing timestamps.
        perl_exception_re: Compiled regex for parsing Perl exceptions.

    Returns:
        A tuple containing:
        - A list of dictionaries, where each dictionary represents a relevant
          log line or exception block. For exceptions, the timestamp is None.
        - A sorted list of unique optional column names found in the logs.
    """
    parsed_log = []
    optional_columns = set()
    lines = log_content.splitlines()
    i = 0
    last_timestamp = None
    while i < len(lines):
        try:
            line = lines[i]
            timestamp_match = timestamp_re.match(line)

            if timestamp_match:
                # This is a standard, timestamped line.
                timestamp = timestamp_match.group(1)
                last_timestamp = timestamp
                # Process it against configured patterns.
                for channel in patterns:
                    pattern = channel.get("pattern")
                    if not pattern:
                        continue

                    search_match = pattern.search(line)
                    if search_match:
                        message = line[len(timestamp_match.group(0)) :].strip()
                        log_entry = {
                            "timestamp": timestamp,
                            "message": message,
                            "type": channel["type"],
                        }
                        group_dict = search_match.groupdict()
                        log_entry.update(group_dict)
                        optional_columns.update(group_dict.keys())
                        parsed_log.append(log_entry)
                        break  # Found a match, go to the next line
                i += 1
            else:
                # This line has no timestamp. It could be the start of an exception block.
                # Collect all following consecutive lines without a timestamp.
                exception_buffer = []
                while i < len(lines) and not timestamp_re.match(lines[i]):
                    if lines[i].strip():  # ignore empty lines
                        exception_buffer.append(lines[i])
                    i += 1

                if exception_buffer:
                    full_buffer_text = "\n".join(exception_buffer)
                    if perl_exception_re.search(full_buffer_text):
                        # Assign a timestamp slightly after the last known event
                        # to position the exception correctly on the timeline.
                        log_entry = {
                            "timestamp": _create_exception_timestamp(last_timestamp),
                            "message": full_buffer_text,
                            "type": "exception",
                        }
                        parsed_log.append(log_entry)
        except Exception as e:
            # Add context to the exception and re-raise it.
            # This will be caught by the `analyze` function's error handler.
            line_content = lines[i] if i < len(lines) else "end of file"
            raise Exception(
                f"Log parsing failed at line {i + 1}: '{line_content}'"
            ) from e

    return parsed_log, sorted(list(optional_columns))
