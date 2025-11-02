# Plan: Multi-Log Parsing and Visualization Feature

This document outlines the plan to implement the multi-log parsing feature, based on the requirements gathered.

## 1. `config.yaml` Structure Changes

To support multiple log parsers per job, the `config.yaml` format will be updated.

### New `log_parsers` Section

A new top-level key, `log_parsers`, will be introduced. It will be a list of parser configurations.
Each of the configuration is specifically associated to one or a family of logfiles, by matching the filename.
Each configuration associated to a log filename has different set of parser to be used
accordingly to the testname that prodiced this specific test file.
For example `autoinst-log.txt` is a log produced by every single job in openQA:
so there will be a parser configuration associated to `autoinst-log.txt`.
Accordingly to the test sequence was running in the job that produced the log,
the set of string to look for in the log can change.
So within a parser configuration there is usually a list of parser, each associated to a test name.
Each parser define a list of channels: each of them is a pattern to look for in the log

Each item in the list will be an object with the following fields:

-   `name`: (String) A user-friendly name for the log, which will be displayed in the UI (e.g., "Serial Terminal Log", "YaST Log").
-   `log_filename`: (String) The exact filename of the log to be downloaded from the openQA server (e.g., `serial-terminal.txt`, `yast2_ncurses.log`).
-   `rules`: (Object) The same structure as the current `autoinst_parser` rules, containing `patterns` and `event_pairs` to be applied to this specific log file.

**Example:**

```yaml
config_ver: 2
log_parsers:
  - name: "Autoinst Log"
    log_filename: "autoinst-log.txt"
    patterns:
      # "autoinst-log.txt" parser for SAPHanaSR jobs
      - name: SAPHanaSR
        # A regular expression used to associate a job with this parser.
        # It must contain a named capture group `(?P<name>...)` which is used to extract a short, human-readable name for display in the UI.
        match_name: |-
          .*(?P<name>SAPHanaSR-ScaleUp-PerfOpt).*
        # A list of channel objects that define the specific log lines to extract as events.
        channels:
          - name: "module_start"
            type: "module"
            pattern: |-
              starting (?P<module>\S+) tests/\S+\.pm

          - name: "module_finish"
            type: "module"
            pattern: |-
              finished (?P<module>\S+) \S+ (runtime: \d+ s)

      # "autoinst-log.txt" parser for multimachine jobs
      - name: multimachine
        # A regular expression used to associate a job with this parser.
        match_name: |-
          .*(?P<name>support_?server|\d?nodes?_?\d+|qnetd_server|sles4sap_ensa_ers_node).*
        # A list of channel objects that define the specific log lines to extract as events.
        channels:
          # Channels for errors
          - name: "error_mutex_lock_owner_finished"
            type: "error"
            pattern: |-
              .*acquiring mutex '(?P<mutex>[^']+)': lock owner already finished
  - name: "Serial terminal"
    log_filename: "serial-terminal.txt"
    patterns:
      # "serial-terminal.txt" parser for SAPHanaSR jobs
      - name: SAPHanaSR
        # A regular expression used to associate a job with this parser.
        # It must contain a named capture group `(?P<name>...)` which is used to extract a short, human-readable name for display in the UI.
        match_name: |-
          .*(?P<name>SAPHanaSR-ScaleUp-PerfOpt).*
        channels:
          - name: "ping command"
            type: "command"
            pattern: |-
              > ping -c \d (?P<ip_address>.*)
```

### Backward Compatibility

To ensure backward compatibility, if the old `autoinst_parser` key is found in `config.yaml`,
it will be automatically treated as a single entry in the new `log_parsers` list.
The application will assume the `log_filename` is `autoinst-log.txt` and the `name` is "Autoinst Log".
`config_ver:` can be also used to detect if format is old or new one

## 2. Backend Changes

### Client (`app/client.py`)

-   The client will be modified to fetch multiple log files.
-   It will read the `log_parsers` list from the configuration.
-   For each job, it will iterate through the configured parsers and download the corresponding `log_filename` for each.
-   To improve performance, log files will be downloaded in parallel using a thread pool.

### Cache (`app/cache.py`)

-   The caching mechanism will be updated to store each downloaded log file separately within the job's cache directory (e.g., `.cache/openqa.suse.de/12345/autoinst-log.txt`, `.cache/openqa.suse.de/12345/yast.log`).
-   The main metadata file for the job (e.g., `_job_details.json`) will be updated to include a list of all successfully cached log file paths associated with that job.

Example of cache file structure:

```json
{
  "job_details": {
        "log_files": ["autoinst-log.txt", "yast.log"]
        }
}
```

### Parsing Logic (`app/autoinst_parser.py`, `app/main.py`)

-   The parsing logic will be generalized to handle multiple logs.
-   The application will iterate through the `log_parsers` configuration. For each log file, it will apply the corresponding set of `rules`.
-   Log parsing will be parallelized using a process or thread pool to improve performance, especially for jobs with many large log files.
-   If a configured log file is not found for a job, the error will be logged on the backend and passed to the frontend for display. The analysis will proceed with the logs that were successfully retrieved.

## 3. Backend-Frontend Data Structure Changes

The JSON payload sent from the backend to the frontend will be restructured to accommodate data from multiple logs.

**Proposed Structure:**

```json
{
  "job_id": 12345,
  "nodes": {
    "0": {
      "merged_timeline_events": [
        { "timestamp": "...", "event": "...", "source_log": "autoinst-log.txt" },
        { "timestamp": "...", "event": "...", "source_log": "yast.log" }
      ],
      "log_results": {
        "autoinst-log.txt": {
          "name": "Autoinst Log",
          "content": [ /* Filtered lines for text view */ ],
          "exceptions": [ /* Exceptions found in this log */ ]
        },
        "yast.log": {
          "name": "YaST Log",
          "content": [ /* Filtered lines for text view */ ],
          "exceptions": []
        }
      }
    }
  },
  "errors": [
    "For job 12345, log file 'missing.log' not found."
  ]
}
```

-   `merged_timeline_events`: A single, time-sorted array containing all events *with timestamps* from all parsed logs. Each event will have a `source_log` property to identify its origin.
-   `log_results`: An object where keys are the log filenames. Each value contains the log's display name and its content (filtered lines, exceptions, etc.) to be displayed in separate text boxes.
-   `errors`: A top-level array for reporting issues like missing log files.

## 4. Frontend Changes

### `main.js` & `renderer.js`

-   The frontend will be updated to process the new JSON data structure.
-   The main rendering logic will iterate through the `log_results` object for each node.
-   For each entry in `log_results`, it will dynamically create a dedicated collapsible box in the UI to display its content (filtered lines, exceptions). This mirrors the current behavior but is now generated dynamically for any number of logs.
-   Any errors in the top-level `errors` array will be displayed in a visible notification area on the page.

### `timelineRenderer.js`

-   The timeline renderer will now receive the `merged_timeline_events` array.
-   It will render all events from this array onto a single, unified timeline.
-   The `source_log` property on each event can be used to add visual cues (e.g., different colors, tooltips) to indicate which log file an event came from.

## 5. E2E and Performance Test Changes

### Performance Tests (`tests/e2e/performance/`)

-   The test data generation script (`synthesize_logs.py` or similar) will be updated to create cache directories that reflect the new multi-log structure, including multiple log files and an updated metadata JSON.
-   New performance test profiles will be added to `log_profiles.yaml` to cover scenarios with multiple log files of varying sizes.
-   The test execution script (`test_analyze.sh`) will be enhanced to run tests that measure the performance of parallel log downloading and parsing, allowing for comparison against the old sequential method.

### E2E Tests (`tests/e2e/playwright/`)

-   The existing Playwright test (`app-loading.spec.ts`) will be updated to align with the new UI.
-   Assertions will be added to:
    -   Verify that the unified timeline is rendered correctly with events from multiple sources.
    -   Confirm that a separate display box is dynamically created for each log file defined in the test data.
    -   Check that the content within each log box is rendered as expected.
    -   Add a new test case to simulate a missing log file and assert that the corresponding error message is displayed on the UI.

## 6. Documentation Updates

The following documents will be updated to reflect the new feature:

-   `config.yaml`: The example configuration will be replaced with one demonstrating the new `log_parsers` list.
-   `docs/configuration.md`: This document will be updated to fully explain the new `log_parsers` section, its fields (`name`, `log_filename`, `rules`), and provide clear examples. The backward compatibility support for the `autoinst_parser` key will also be documented.
-   `README.md`: The main README will be updated to mention the new capability of parsing multiple logs per job.
-   `specs/001-log-synthetizer-this/spec.md`: The specification document will be reviewed and updated to reflect the final implementation details.
