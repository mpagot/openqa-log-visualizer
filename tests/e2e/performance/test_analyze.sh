#!/bin/bash

# A simple e2e performance test for the /analyze endpoint.

# -e: Exit immediately if a command exits with a non-zero status.
# -o pipefail: Exit immediately if a pipeline fails.
# -u: Exit immediately if an undeclared variable is used.
set -eou pipefail
# -x: Print every command before executing it.
#set -x

# --- Argument Parsing ---
CONFIG_FILENAME=""
LOGS_DIRNAME=""
RUN_SAMPLES=1 # Default value

while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    -c)
      CONFIG_FILENAME="$2"
      shift 2
      ;;
    -l)
      LOGS_DIRNAME="$2"
      shift 2
      ;;
    --run-sample)
      if [ -n "$2" ] && [[ "$2" =~ ^[0-9]+$ ]] && [ "$2" -gt 0 ]; then
        RUN_SAMPLES="$2"
        shift 2
      else
        echo "[ERROR] --run-sample requires a positive integer argument." >&2
        exit 1
      fi
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# --- Configuration ---
# Validate and set the full path for the config file
if [ -z "$CONFIG_FILENAME" ]; then
  echo "[ERROR] Config file not specified. Use -c <filename>" >&2
  exit 1
fi
PERF_ASSETS_DIR="tests/e2e/performance/assets"
CONFIG_FILE_PATH="${PERF_ASSETS_DIR}/configs/${CONFIG_FILENAME}"
if [ ! -f "$CONFIG_FILE_PATH" ]; then
    echo "[ERROR] Config file not found at: ${CONFIG_FILE_PATH}" >&2
    exit 1
fi

# Validate and set the full path for the logs directory
if [ -z "$LOGS_DIRNAME" ]; then
  echo "[ERROR] Logs directory not specified. Use -l <dirname>" >&2
  exit 1
fi
LOGS_DIR_PATH="${PERF_ASSETS_DIR}/logs/${LOGS_DIRNAME}"
if [ ! -d "$LOGS_DIR_PATH" ]; then
    echo "[ERROR] Logs directory not found at: ${LOGS_DIR_PATH}" >&2
    exit 1
fi
JOB_URL="https://__ginopino__/tests/19016820#next_previous"
HOST="127.0.0.1"
PORT="5001"
STARTUP_WAIT="3"

# The final, machine-readable results will be stored here.
FINAL_RESULTS_FILE="performance_results.jsonl"
MONITOR_PID=""

# Create a temporary directory for intermediate files for each run.
OUTPUT_DIR=$(mktemp -d)

# Define the path for the temporary config file for this run.
TEMP_CONFIG_PATH="${OUTPUT_DIR}/config.yaml"

# -- prepare a config.yaml and a cache ---
# Copy the user-selected config file to the temp directory to avoid modifying the original.
echo "[DEBUG] Copying source config \'$CONFIG_FILE_PATH\' to \'$TEMP_CONFIG_PATH\'" >&2
cp "$CONFIG_FILE_PATH" "$TEMP_CONFIG_PATH"
# Modify the temporary config file to set the cache_dir to the user-selected log directory.
# This forces the application to use the pre-populated cache for the test.
# First, remove any existing 'cache:' block to prevent duplicates.
sed -i '/^cache:/d' "$TEMP_CONFIG_PATH"

# Now, append the new cache configuration.
echo "[DEBUG] Setting cache_dir in \'$TEMP_CONFIG_PATH\' to \'$LOGS_DIR_PATH\'" >&2
echo "" >> "$TEMP_CONFIG_PATH" # Add a newline for safety
echo "cache:" >> "$TEMP_CONFIG_PATH"
echo "  cache_dir: \"${LOGS_DIR_PATH}\"" >> "$TEMP_CONFIG_PATH"


# Define paths for intermediate files.
CURL_METRICS_JSON="${OUTPUT_DIR}/curl_metrics.json"
SERVER_LOG_FILE="${OUTPUT_DIR}/server.log"
OS_METRICS_CSV="${OUTPUT_DIR}/os_metrics.csv"

# --- Functions ---

# Starts the server, performs a health check, and returns the PID.
# Exits the script if the server fails to start.
# Arguments:
#   $1: Path to the config.yaml file.
# Returns:
#   The PID of the started server process.
function start_server() {
  local config_file=$1

  #echo "[DEBUG] Inside start_server function using CONFIG_FILE=${config_file}." >&2
  #echo "[DEBUG] Executing: OQTV_CONFIG_FILE='$TEMP_CONFIG_PATH' uv run flask --app app.main run --host='$HOST' --port='$PORT' --debug" >&2
  # Redirect both stdout and stderr to the server log file. This is crucial for capturing all output from the background server process, including any errors.
  OQTV_CONFIG_FILE="$TEMP_CONFIG_PATH" uv run flask --app app.main run --host="$HOST" --port="$PORT" --debug > "$SERVER_LOG_FILE" 2>&1 &
  local pid=$!
  sleep "$STARTUP_WAIT"

  if ! ps -p "$pid" > /dev/null; then
    echo "[ERROR] Server failed to start. Check logs in ${SERVER_LOG_FILE}" >&2
    cat "$SERVER_LOG_FILE" >&2
    exit 1
  fi

  echo "$pid"
}

# Safely stops a process by its PID.
# Arguments:
#   $1: The PID of the process to stop.
#   $2: The name of the process (for logging).
function stop_process() {
    local pid=$1
    local name=$2

    echo "[DEBUG] Stop process ${name} pid ${pid}" >&2

    if [ -n "$pid" ] && ps -p "$pid" > /dev/null; 
    then
        echo "[DEBUG] Stopping ${name} (PID: ${pid})..." >&2
        set +e
        kill "$pid"
        wait "$pid" 2>/dev/null
        set -e
    fi
    echo "[DEBUG] Stop done" >&2
}


# Assesses the health of a sample and reports details on failure.
# Does not perform any process management (like kill).
# Arguments:
#   $1: curl exit code
#   $2: http response code
#   $3: server process health ("true" or "false")
# Returns 0 if healthy, 1 if unhealthy.
function check_sample_health() {
  local curl_exit_code=$1
  local http_code=$2
  local server_is_alive=$3

  if [ "$curl_exit_code" -eq 0 ] && [ "$http_code" -eq 200 ] && [ "$server_is_alive" == "true" ]; then
    return 0 # Success
  fi

  # --- If we reach here, the sample is unhealthy ---
  echo "[ERROR] Sample FAILED. See details below." >&2

  echo "[ERROR] --- Failure Analysis ---" >&2
  if [ "$server_is_alive" == "false" ]; then
    echo "Health Check: FAILED - Server process crashed or exited prematurely." >&2
  else
    echo "Health Check: OK - Server process is still running." >&2
  fi
  echo "Curl Exit Code: $curl_exit_code (Expected: 0)" >&2
  echo "HTTP Response Code: $http_code (Expected: 200)" >&2
  echo

  echo "--- Server Log (from $SERVER_LOG_FILE) ---" >&2
  cat "$SERVER_LOG_FILE"
  echo "[ERROR] --------------------------------------------------" >&2

  return 1 # Failure
}


# --- Cleanup Function ---
cleanup() {
  echo "[DEBUG] Running cleanup..." >&2
  # Note: `${VAR:-}` is used to provide an empty string if the variable is
  # unset. This is crucial because this cleanup function is called by a `trap`
  # on EXIT, which includes normal script termination. After the last sample
  # loop, SERVER_PID is unset, so this prevents an "unbound variable" error
  # when `set -u` is active.
  stop_process "${SERVER_PID:-}" "server"
  stop_process "${MONITOR_PID:-}" "monitor"
 
  echo "[DEBUG] Removing temporary directory: $OUTPUT_DIR" >&2
  #rm -rf "$OUTPUT_DIR"
  echo "[DEBUG] Test finished." >&2
}

# Register the cleanup function to be called when the script exits.
trap cleanup EXIT

# --- Main Execution ---
# Initialize the results file by removing the old one.
echo "[DEBUG] Initializing results file: $FINAL_RESULTS_FILE" >&2
rm "${FINAL_RESULTS_FILE}" || echo "[DEBUG] No result to clean up" >&2
HEALTHY_SAMPLES_COUNT=0

# Capture environment details once per script run.
GIT_COMMIT=$(git rev-parse HEAD)
CPU_MODEL=$(lscpu | grep 'Model name' | sed 's/.*Model name:[[:space:]]*//')
CPU_CORES=$(nproc)
MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
OS_INFO=$(uname -s -r)

ENV_JSON=$(jq -n \
  --arg commit "$GIT_COMMIT" \
  --arg config_name "$CONFIG_FILENAME" \
  --arg logs_dirname "$LOGS_DIRNAME" \
  --arg cpu_model "$CPU_MODEL" \
  --argjson cpu_cores "$CPU_CORES" \
  --argjson mem_kb "$MEM_TOTAL_KB" \
  --arg os "$OS_INFO" \
  '{env_details: {git_commit: $commit, config_name: $config_name, logs_dirname: $logs_dirname, machine_specs: {cpu_model: $cpu_model, cpu_cores: $cpu_cores, total_memory_kb: $mem_kb, os: $os}}}') 

for i in $(seq 1 $RUN_SAMPLES)
do
  # Clear intermediate files for this new run.
  # The ':>' syntax is a POSIX-compliant way to truncate a file to zero length
  # or create it if it doesn't exist. The ':' is a built-in no-op command.
  :> "$OS_METRICS_CSV"
  :> "$CURL_METRICS_JSON"

  echo "[DEBUG] --- Running Sample $i / $RUN_SAMPLES ---" >&2

  echo "[DEBUG] About to call start_server..." >&2
  # --- Start Server ---
  SERVER_PID=$(start_server "$TEMP_CONFIG_PATH")
  echo "[DEBUG] ...start_server finished. PID is $SERVER_PID" >&2

  # --- Start System Monitoring ---
  while ps -p $SERVER_PID > /dev/null; do
    ps -p $SERVER_PID -o %cpu,rss --no-headers >> "$OS_METRICS_CSV"
    sleep 0.2
  done &
  MONITOR_PID=$!

  # --- Run Test ---
  JSON_PAYLOAD=$(printf '{"log_url": "%s", "ignore_cache": false}' "$JOB_URL")
  CURL_WRITE_OUT='{"curl_metrics": {
        "http_code": %{http_code},
        "time_total_s": %{time_total},
        "time_namelookup_s": %{time_namelookup},
        "time_connect_s": %{time_connect},
        "time_pretransfer_s": %{time_pretransfer},
        "time_starttransfer_s": %{time_starttransfer}
    }}'
  # The --fail flag ensures curl exits with a non-zero status on server errors (4xx, 5xx).
  curl --request POST \
    --url "http://${HOST}:${PORT}/analyze" \
    --header "Content-Type: application/json" \
    --data "${JSON_PAYLOAD}" \
    --output /dev/null \
    --write-out "${CURL_WRITE_OUT}" \
    --silent --fail > "$CURL_METRICS_JSON"
  CURL_EXIT_CODE=$?

  # --- Stop System Monitoring ---
  stop_process "$MONITOR_PID" "monitor"
  
  # --- Health Check and Process Results ---
  # It is possible for the metrics file to be empty if curl fails early, so we check.
  HTTP_CODE=$(jq '.curl_metrics.http_code' "$CURL_METRICS_JSON" 2>/dev/null || echo "0")
  SERVER_IS_ALIVE="false"
  if ps -p "$SERVER_PID" > /dev/null; then
    SERVER_IS_ALIVE="true"
  fi

  if check_sample_health "$CURL_EXIT_CODE" "$HTTP_CODE" "$SERVER_IS_ALIVE"; then
    # --- Process and Save Results ---
    stop_process "$SERVER_PID" "server"
    
    BACKEND_PERF_JSON=$(awk '/--- Performance Metrics ---/{flag=1; next} /---------------------------/{flag=0} flag' "$SERVER_LOG_FILE" | sed '1s/.*INFO in main: //')
    if [ -z "$BACKEND_PERF_JSON" ]; then
      echo "[WARNING] Could not find backend performance metrics for sample $i. Skipping." >&2
      continue
    fi

    read PEAK_CPU PEAK_MEM_KB < <(awk '{ if($1>max_cpu) max_cpu=$1; if($2>max_mem) max_mem=$2 } END { print max_cpu, max_mem }' "$OS_METRICS_CSV")
    OS_METRICS_JSON=$(printf '{"os_metrics":{"peak_cpu_percent":%.2f,"peak_memory_kb":%d}}' "${PEAK_CPU:-0}" "${PEAK_MEM_KB:-0}")
        # Extract metadata from the backend JSON to create the run_health object.
    CACHE_HITS=$(echo "$BACKEND_PERF_JSON" | jq '.cache_hits')
    PARSED_JOB_IDS=$(echo "$BACKEND_PERF_JSON" | jq '[.log_parsing[].job_id]')
    RUN_HEALTH_JSON=$(jq -n \
      --argjson curl_exit "$CURL_EXIT_CODE" \
      --argjson http "$HTTP_CODE" \
      --arg alive "$SERVER_IS_ALIVE" \
      --argjson cache_hits "$CACHE_HITS" \
      --argjson job_ids "$PARSED_JOB_IDS" \
      '{run_health: {curl_exit_code: $curl_exit, http_code: $http, server_is_alive: $alive, cache_hits: $cache_hits, parsed_job_ids: $job_ids}}')

    CURL_PERF_JSON=$(jq '.' "$CURL_METRICS_JSON")

    # Merge all JSON objects into the final record for this run.
    COMBINED_JSON=$(jq -c -s '.[0] * .[1] * .[2] * .[3] + {backend_metrics: .[4]}' \
      <(echo "$CURL_PERF_JSON") \
      <(echo "$OS_METRICS_JSON") \
      <(echo "$RUN_HEALTH_JSON") \
      <(echo "$ENV_JSON") \
      <(echo "$BACKEND_PERF_JSON"))

    echo "$COMBINED_JSON" >> "$FINAL_RESULTS_FILE"
    echo "[DEBUG] Sample $i complete. Results appended to $FINAL_RESULTS_FILE." >&2
    HEALTHY_SAMPLES_COUNT=$((HEALTHY_SAMPLES_COUNT + 1))
  else
    # --- Handle Invalid Sample ---
    # The health check function already printed the failure details.
    stop_process "$SERVER_PID" "server"
    echo "[WARNING] Sample $i was unhealthy and has been skipped." >&2
  fi
  # Unset SERVER_PID after it has been handled in either the if or else block.
  unset SERVER_PID

done

# --- Final Message ---
echo "======================================================================"
echo "All $RUN_SAMPLES samples attempted. $HEALTHY_SAMPLES_COUNT were successful."
echo "Machine-readable results saved to: $FINAL_RESULTS_FILE"
