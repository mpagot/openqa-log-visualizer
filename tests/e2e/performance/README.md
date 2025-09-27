# Backend Performance Testing Suite

This directory contains a suite of tools for end-to-end performance testing of the application's backend.
It provides a reliable way to benchmark performance, detect regressions,
and analyze the impact of code changes on key metrics like response time and memory usage.

## Purpose

The primary goal of this toolkit is to enable reliable and repeatable performance testing
by isolating the backend's performance from external variables.
Instead of relying on live API calls and network conditions, it uses a controlled environment
with a standard suite of generated log files.
This ensures that any measured changes in performance are a direct result of changes to the application code itself.

## Components

The testing suite consists of three scripts that work together:

### 1. `synthesize_logs.py` (The Data Generator)

This script generates consistent, version-controllable test data. It creates synthetic `autoinst-log.txt` files with specific,
predefined characteristics.

-   **Profile-Driven**: It reads `log_profiles.yaml` to determine what kinds of logs to create
                        (e.g., long files with sparse matches, short files with dense matches).
-   **Regex-Aware**: It uses the regex patterns from a specified `config.yaml` file to generate lines
                     that are guaranteed to match, allowing for the simulation of different parsing complexities.
-   **Consistent Output**: It produces a standard set of log files in the correct cache structure (`<output_dir>/__ginopino__/<job_id>.autoinst-log.txt`),
                           ensuring that every test run uses the exact same data.

### 2. `test_analyze.sh` (The Test Runner)

This is the central orchestrator of the performance test. It runs a test against the `/analyze` endpoint in a controlled and repeatable manner.

-   **Environment Control**: It forces the application to use a specific, pre-populated cache directory, eliminating variability from the network.
-   **Orchestration**: It starts the Flask server, waits for it to be ready, and then executes the test.
-   **System Monitoring**: While the test runs, it records the server's CPU and memory usage.
-   **Metric Collection**: It uses `curl` to capture detailed network timing metrics and extracts
                           the application's own `backend_metrics` from the server logs.
-   **Data Aggregation**: It combines all collected data (curl, OS, backend, git commit, etc.) into a single JSON object
                          for each run and appends it to `performance_results.jsonl`.
-   **Statistical Sampling**: It can run the test multiple times (`--run-sample`) to gather data for statistical analysis.

### 3. `compare_perf.py` (The Reporter)

This script is the final analysis tool. It takes two `performance_results.jsonl` files (a "base" run and a "new" run) and provides a clear, human-readable comparison.

-   **Statistical Analysis**: It calculates the mean, median, standard deviation, and p95 percentile for key metrics, providing a statistically sound view of performance.
-   **Environment Check**: It intelligently warns you if the tests were run on different hardware or with different configurations, which could invalidate the comparison.
-   **Regression/Improvement Reporting**: It generates a color-coded report that clearly shows the percentage change for each metric, flagging significant changes as a **(REGRESSION)** in red or an **(IMPROVEMENT)** in green.

## How to Run a Performance Test

Here is the standard workflow for using the toolkit to measure the impact of a code change.

### Step 1: Generate Test Data

First, generate the standard set of synthetic logs. You only need to do this once, unless you change the log profiles or the regex configuration.

```bash
cd tests/e2e/performance
uv run synthesize_logs.py \
    --config assets/configs/config.performance.yaml \
    --output-dir assets/logs
```

### Step 2: Establish a Baseline

Before making any code changes, run the test on your `main` or baseline branch to get a baseline performance measurement.
We'll run it 10 times for statistical significance.

**IMPORTANT**: This script must be executed from the root of the project directory.

```bash
# Run the test using the 'performance' config and the 'long_sparse' log profile (job_id: 0)
tests/e2e/performance/test_analyze.sh \
    -c config.performance.yaml \
    -l 1 \
    --run-sample 10

# Rename the results file to save it as your baseline
mv performance_results.jsonl base_results.jsonl
```

### Step 3: Make Your Code Changes

Implement your feature, bug fix, or refactoring in the application's backend or frontend code.

### Step 4: Run the Test Again

After making your changes, run the exact same test again to generate a new set of results.

```bash
tests/e2e/performance/test_analyze.sh -c config.performance.yaml -l 1 --run-sample 10
```

This will create a new `performance_results.jsonl` file containing the metrics for your new code.

### Step 5: Compare the Results

Finally, use the `compare_perf.py` script to see a clear report on the performance impact of your changes.

```bash
python tests/e2e/performance/compare_perf.py base_results.jsonl performance_results.jsonl
```

### Interpreting the Results

The output will show you the percentage change between the base and new runs.

-   A **<font color='green'>green (IMPROVEMENT)</font>** indicates your change made the application faster or more efficient.
-   A **<font color='red'>red (REGRESSION)</font>** indicates your change made it slower or less efficient.
-   Pay close attention to the **standard deviation (`stdev`)**. A large increase in this value is a regression, as it indicates performance has become less consistent, even if the average time is the same.
