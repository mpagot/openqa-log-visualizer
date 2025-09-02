import re
from app.autoinst_parser import parse_autoinst_log


def test_parse_autoinst_log():
    """Tests the main log parsing function with a variety of log line types."""
    log_content = """
[2025-09-01T10:00:00.000Z] [debug] mutex create 'test_mutex'
[2025-09-01T10:00:01.000Z] [info] Some other log line
[2025-09-01T10:00:02.000Z] [debug] mutex lock 'test_mutex'
Can't call method "click" on an undefined value at /usr/lib/os-autoinst/consoles/VNC.pm line 123.
...
[2025-09-01T10:00:03.000Z] [debug] mutex unlock 'test_mutex'
    """
    patterns = [
        {
            "name": "mutex_create",
            "type": "mutex",
            "pattern": re.compile(r"mutex create '(?P<mutex>[^']+)'"),
        },
        {
            "name": "mutex_lock",
            "type": "mutex",
            "pattern": re.compile(r"mutex lock '(?P<mutex>[^']+)'"),
        },
        {
            "name": "mutex_unlock",
            "type": "mutex",
            "pattern": re.compile(r"mutex unlock '(?P<mutex>[^']+)'"),
        },
    ]
    timestamp_re = re.compile(r"^\[([^\]]+)\]")
    perl_exception_re = re.compile(r" at .*?\.pm line \d+")

    parsed_log, optional_columns, line_count, match_count = parse_autoinst_log(
        log_content, patterns, timestamp_re, perl_exception_re
    )

    assert line_count == len(log_content.splitlines())
    assert match_count == 4
    assert len(parsed_log) == 4
    assert optional_columns == ["mutex"]

    # Test mutex create
    assert parsed_log[0]["timestamp"] == "2025-09-01T10:00:00.000Z"
    assert parsed_log[0]["event_name"] == "mutex_create"
    assert parsed_log[0]["mutex"] == "test_mutex"

    # Test mutex lock
    assert parsed_log[1]["timestamp"] == "2025-09-01T10:00:02.000Z"
    assert parsed_log[1]["event_name"] == "mutex_lock"
    assert parsed_log[1]["mutex"] == "test_mutex"

    # Test exception
    assert parsed_log[2]["type"] == "exception"
    assert "Can't call method" in parsed_log[2]["message"]
    assert parsed_log[2]["timestamp"] is not None  # Should have an offset timestamp

    # Test mutex unlock
    assert parsed_log[3]["timestamp"] == "2025-09-01T10:00:03.000Z"
    assert parsed_log[3]["event_name"] == "mutex_unlock"
    assert parsed_log[3]["mutex"] == "test_mutex"

