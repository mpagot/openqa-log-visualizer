# Contributing to the openQA Log Visualizer

First off, thank you for considering contributing! As this project is currently a **Proof of Concept (PoC)**, your feedback and contributions are invaluable in shaping its development.

## How to Contribute

There are many ways to contribute, from writing code to submitting bug reports and feature requests.

### Providing Feedback

This is the most valuable contribution you can make at this stage. Please share your thoughts on:

*   **New Features:** What would make this tool a must-have for your daily work?
*   **Usability:** Is the timeline easy to use? Is anything confusing?
*   **Documentation:** Is the documentation clear? What's missing?

The best way to share your thoughts is by [opening an issue on GitHub](https://github.com/your-username/your-repository/issues).

### Reporting Bugs

If you find a bug, please open an issue and provide the following information:

*   A clear and descriptive title.
*   The full URL of the openQA job you were analyzing.
*   The full debug log from the application's web UI.
*   A description of the bug and what you expected to happen.

### Submitting Pull Requests

If you'd like to contribute code, please feel free to fork the repository and submit a pull request. Here are a few guidelines:

1.  **Create an issue:** Before starting work on a new feature or a significant change, please open an issue to discuss it first.
2.  **Follow the existing code style.**
3.  **Write tests:** If you add new functionality, please add tests to cover it.

## Development Setup

### Prerequisites

*   Python 3.9 or newer
*   [uv](https://github.com/astral-sh/uv) - An extremely fast Python package installer and resolver.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd openqa-log-visualizer
    ```

2.  **Install the python dependencies:**
    This project uses `uv` to manage dependencies. The first time you run a command with `uv run`, it will automatically create a virtual environment and install the required packages from `pyproject.toml`.

## Running the Tests

This project contains both backend (Python) and frontend (JavaScript) tests.

### Backend Tests

The backend tests use `pytest`. To run them, use the following command from the root of the project:

```bash
uv run pytest tests/backend/
```

### Frontend Tests
The frontend unit tests use Vitest and require Node.js and npm to be installed.

#### Setup
The project's frontend dependencies are defined in package.json. To install them, you can run:

```bash
npm install
```

#### Running
A `Makefile` is provided to simplify running the tests. This command will automatically install the dependencies if they are not already present, and then run the test suite:

```bash
make test-frontend
```