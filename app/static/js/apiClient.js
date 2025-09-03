export class ApiClient {
    /**
     * Sends an analysis request to the backend.
     * @param {string} logUrl - The URL of the log to analyze.
     * @param {boolean} ignoreCache - Whether to ignore the server-side cache.
     * @returns {Promise<object>} A promise that resolves with the analysis data.
     */
    analyze(logUrl, ignoreCache) {
        return fetch('/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ log_url: logUrl, ignore_cache: ignoreCache })
        })
        .then(response => {
            if (!response.ok) {
                return response.json()
                    .catch(() => {
                        throw new Error(`HTTP error! Status: ${response.status} ${response.statusText}`);
                    })
                    .then(errorData => {
                        throw new Error(errorData.error || `HTTP error! Status: ${response.status}`);
                    });
            }
            return response.json();
        });
    }
}

