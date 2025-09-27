import json
import statistics
import sys
from math import ceil


# ANSI color codes for highlighting output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

def get_metric(record, metric_path):
    """Safely retrieve a nested metric from a record using a dot-separated path."""
    keys = metric_path.split('.')
    value = record
    for key in keys:
        try:
            value = value[key]
        except (KeyError, TypeError):
            return None
    return value

def load_results(filepath):
    """Load a .jsonl file into a list of dictionaries."""
    results = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
    except FileNotFoundError:
        print(f"{Colors.RED}Error: File not found at '{filepath}'.{Colors.ENDC}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"{Colors.RED}Error: Invalid JSON in '{filepath}': {e}{Colors.ENDC}")
        sys.exit(1)
    if not results:
        print(f"{Colors.YELLOW}Warning: No data found in '{filepath}'.{Colors.ENDC}")
    return results

def calculate_stats(results, metric_path):
    """Calculate mean, median, stdev, and p95 for a given metric."""
    values = [get_metric(r, metric_path) for r in results]
    values = [v for v in values if v is not None and isinstance(v, (int, float))]

    if not values:
        return { 'mean': None, 'median': None, 'stdev': None, 'p95': None, 'count': 0 }

    count = len(values)
    mean = statistics.mean(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if count > 1 else 0

    # Simple percentile calculation (nearest-rank)
    values.sort()
    p95_index = ceil(0.95 * count) - 1
    p95 = values[p95_index] if count > 0 else None

    return { 'mean': mean, 'median': median, 'stdev': stdev, 'p95': p95, 'count': count }

def compare_environments(base_results, new_results):
    """Check if the testing environments are consistent."""
    base_env = get_metric(base_results[0], 'env_details.machine_specs')
    new_env = get_metric(new_results[0], 'env_details.machine_specs')

    if base_env != new_env:
        print(f"{Colors.YELLOW}--- WARNING: Environment Mismatch ---")
        print("Machine specs differ between result sets. Comparison may be unreliable.")
        # Optionally, print the differing specs
        # for key in base_env:
        #     if base_env.get(key) != new_env.get(key):
        #         print(f"  - {key}: '{base_env.get(key)}' (base) vs '{new_env.get(key)}' (new)")
        print(f"------------------------------------{Colors.ENDC}")
        print()

def print_report(base_stats, new_stats, metric_name, unit, is_timing=True):
    """Print a single line of the comparison report."""
    base_mean = base_stats['mean']
    new_mean = new_stats['mean']

    if base_mean is None or new_mean is None:
        print(f"{metric_name:<25} {str(base_mean or 'N/A'):<20} {str(new_mean or 'N/A'):<20} N/A")
        return

    change = ((new_mean - base_mean) / base_mean) * 100 if base_mean != 0 else float('inf')
    
    color = Colors.ENDC
    indicator = "(neutral)"
    if abs(change) > 5: # Only color significant changes
        if (is_timing and change > 0) or (not is_timing and change < 0):
            color = Colors.RED
            indicator = "(REGRESSION)"
        else:
            color = Colors.GREEN
            indicator = "(IMPROVEMENT)"

    base_str = f"{base_mean:.3f} {unit}"
    new_str = f"{new_mean:.3f} {unit}"
    change_str = f"{color}{change:+.1f}% {indicator}{Colors.ENDC}"

    print(f"{metric_name:<25} {base_str:<20} {new_str:<20} {change_str}")

def main():
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <base_results.jsonl> <new_results.jsonl>")
        sys.exit(1)

    base_filepath = sys.argv[1]
    new_filepath = sys.argv[2]

    base_results = load_results(base_filepath)
    new_results = load_results(new_filepath)

    if not base_results or not new_results:
        print("Cannot generate comparison with empty result sets.")
        sys.exit(1)

    compare_environments(base_results, new_results)

    base_commit = get_metric(base_results[0], 'env_details.git_commit')[:8]
    new_commit = get_metric(new_results[0], 'env_details.git_commit')[:8]

    print("Comparing Performance:")
    print(f"  {Colors.BLUE}Base:{Colors.ENDC} {base_commit} ({base_filepath})")
    print(f"  {Colors.BLUE}New:{Colors.ENDC}  {new_commit} ({new_filepath})")
    print()

    print(f"{'Metric':<25} { 'Base (avg)':<20} { 'New (avg)':<20} {'Change'}")
    print("-" * 80)

    metrics_to_compare = {
        "Time Total (s)": ("curl_metrics.time_total_s", "s", True),
        "Peak Memory (KB)": ("os_metrics.peak_memory_kb", "KB", True),
        "Log Processing (s)": ("backend_metrics.log_processing_duration", "s", True),
        "Event Pairing (s)": ("backend_metrics.event_pairing.duration", "s", True),
        "Response Size (Bytes)": ("backend_metrics.response_size_bytes", "B", True),
    }

    for name, (path, unit, is_timing) in metrics_to_compare.items():
        base_stats = calculate_stats(base_results, path)
        new_stats = calculate_stats(new_results, path)
        print_report(base_stats, new_stats, name, unit, is_timing)

    print("-" * 80)

if __name__ == "__main__":
    main()