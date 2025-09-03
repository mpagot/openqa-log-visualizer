/**
 * @module renderer
 * @description
 * This module is responsible for all direct DOM manipulation and rendering
 * of the main content areas, including job details and debug logs. It follows
 * a "dumb" component pattern, where it receives data and renders it without
 * containing any application logic or state management.
 *
 * Responsibilities:
 * - Clearing the UI before new data is rendered.
 * - Rendering loading and error states.
 * - Rendering the debug log panel.
 * - Rendering the detailed, collapsible sections for each job.
 * - Toggling the visibility of floating UI controls.
 */

/**
 * Creates a collapsible <details> section with a <table> inside.
 * This is an internal helper function.
 * @param {string} title - The title for the <summary> element.
 * @param {object|Array} data - The data to display in the table.
 * @param {string} [jobId] - The job ID, used for creating unique IDs for log rows.
 * @returns {HTMLDetailsElement} The created <details> element.
 */
function _createCollapsibleSection(title, data, jobId) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = title;
    details.appendChild(summary);

    // The content might be a string (for errors)
    if (typeof data === 'string') {
        const pre = document.createElement('pre');
        pre.textContent = data;
        details.appendChild(pre);
        return details;
    }

    const table = document.createElement('table');

    if (title === 'Settings' && typeof data === 'object' && !Array.isArray(data)) {
        const tbody = document.createElement('tbody');
        // Sort keys for consistent order
        for (const [key, value] of Object.entries(data).sort()) {
            const row = tbody.insertRow();
            const keyCell = row.insertCell();
            keyCell.textContent = key;
            keyCell.className = 'settings-key';

            const valueCell = row.insertCell();
            valueCell.textContent = value;
            valueCell.className = 'settings-value';
        }
        table.appendChild(tbody);
        details.appendChild(table);
    } else if (title === 'autoinst-log') {
        const content = data['autoinst-log'];
        const optionalColumns = data['optional_columns'] || [];

        if (!Array.isArray(content)) {
            const pre = document.createElement('pre');
            pre.textContent = content;
            details.appendChild(pre);
            return details;
        }

        table.className = 'autoinst-log-table';
        const thead = document.createElement('thead');
        const headerRow = thead.insertRow();
        let columns = [
            { name: 'Timestamp', key: 'timestamp', class: 'col-timestamp' },
            { name: 'Type', key: 'type', class: 'col-type' },
        ];

        optionalColumns.forEach(colKey => {
            const colName = colKey.charAt(0).toUpperCase() + colKey.slice(1).replace(/_/g, ' ');
            columns.push({
                name: colName,
                key: colKey,
                class: `col-${colKey}`
            });
        });

        columns.push({ name: 'Message', key: 'message', class: 'col-message' });

        columns.forEach(col => {
            const th = document.createElement('th');
            th.textContent = col.name;
            th.className = col.class;
            headerRow.appendChild(th);
        });
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        content.forEach((logEntry, index) => {
            const row = tbody.insertRow();
            row.id = `log-row-${jobId}-${index}`;
            columns.forEach(col => {
                const cell = row.insertCell();
                const cellValue = logEntry[col.key] || '';
                let cellText = cellValue;

                // For exceptions, show only the first significant line in the table.
                if (col.key === 'message' && logEntry.type === 'exception') {
                    const match = cellText.match(/.* at .*?\.pm line \d+\.?/);
                    if (match) {
                        cellText = match[0];
                    } else {
                        cellText = cellText.split('\n')[0];
                    }

                    const exceptionIndex = data.exceptions.findIndex(ex => ex.log_index === index);
                    if (exceptionIndex !== -1) {
                        const link = document.createElement('a');
                        link.href = `#exception-row-${jobId}-${exceptionIndex}`;
                        link.textContent = cellText;
                        cell.appendChild(link);
                       return; // Skip default textContent assignment
                    }
                }
                cell.textContent = cellText;
                cell.className = col.class;
            });
        });
        table.appendChild(tbody);
        details.appendChild(table);
    } else if (title === 'Exceptions') {
        const exceptions = data.exceptions || [];
        table.style.width = '100%';
        const tbody = document.createElement('tbody');
        exceptions.forEach((exception, index) => {
            const row = tbody.insertRow();
            row.id = `exception-row-${jobId}-${index}`;
            const cell = row.insertCell();

            const backLinkContainer = document.createElement('div');
            backLinkContainer.style.marginBottom = '0.5em';
            const backLink = document.createElement('a');
            backLink.href = `#log-row-${jobId}-${exception.log_index}`;
            backLink.textContent = `[Go to log line ${exception.log_index + 1}]`;
            backLinkContainer.appendChild(backLink);
            cell.appendChild(backLinkContainer);

            // Using <pre> preserves whitespace and newlines from the exception text
            const pre = document.createElement('pre');
            pre.textContent = exception.message;
            // Reset some default <pre> styling to make it look better in a table cell
            pre.style.margin = '0';
            pre.style.padding = '0';
            pre.style.border = 'none';
            pre.style.backgroundColor = 'transparent';
            cell.appendChild(pre);
        });
        table.appendChild(tbody);
        details.appendChild(table);
    } else {
        // Fallback to <pre> for other content
        const pre = document.createElement('pre');
        pre.textContent = JSON.stringify(data, null, 2);
        details.appendChild(pre);
    }
    return details;
}

/**
 * Renders a loading message into a specified container.
 * @param {HTMLElement} container - The container element to render into.
 */
export function renderLoading(container) {
    container.innerHTML = '<pre>Analyzing...</pre>';
}

/**
 * Clears the content of specified UI elements.
 * @param {Object.<string, HTMLElement>} elements - An object containing the DOM elements to clear.
 */
export function clearUI(elements) {
    elements.jobDetailsContainer.innerHTML = '';
    elements.timelineContainer.innerHTML = '';
    elements.debugLogContent.innerHTML = '';
}

/**
 * Renders an error message into a specified container.
 * @param {string} message - The error message to display.
 * @param {HTMLElement} container - The container element to render into.
 */
export function renderError(message, container) {
    const errorPre = document.createElement('pre');
    errorPre.textContent = `Error: ${message}`;
    container.appendChild(errorPre);
}

/**
 * Renders the debug log into its container.
 * @param {Array<object>} logs - The array of log objects from the backend.
 * @param {HTMLElement} container - The container element for the debug log.
 */
export function renderDebugLog(logs, container) {
    container.innerHTML = ''; // Clear previous logs
    if (logs && Array.isArray(logs)) {
        logs.forEach(log => {
            const logEntry = document.createElement('div');
            logEntry.textContent = `[${log.level.toUpperCase()}] ${log.message}`;
            logEntry.className = `log-${log.level}`; // Assign class for styling
            container.appendChild(logEntry);
       });
    }
}

/**
 * Renders the details for all jobs into the main container.
 * @param {Object} jobsData - The jobs object from the backend response.
 * @param {HTMLElement} container - The main container for job details.
 */
export function renderJobDetails(jobsData, container) {
    for (const jobId in jobsData) {
        const jobDetails = jobsData[jobId];

        const jobDiv = document.createElement('div');
        jobDiv.className = 'job-entry';

        const title = document.createElement('h3');
        const jobLink = document.createElement('a');
        jobLink.href = jobDetails.job_url;
        jobLink.textContent = jobId;
        jobLink.target = '_blank';
        jobLink.rel = 'noopener noreferrer';

        title.appendChild(jobLink);

        if (jobDetails.error) {
            title.append(` - Error fetching details`);
        } else {
            title.append(` - ${jobDetails.short_name}`);
            if (jobDetails.parser_name) {
                const parserSpan = document.createElement('span');
                parserSpan.textContent = ` [Parser: ${jobDetails.parser_name}]`;
                parserSpan.style.color = '#888';
                parserSpan.style.fontStyle = 'italic';
                title.appendChild(parserSpan);
            }
            if (jobDetails.is_cached) {
                const cachedSpan = document.createElement('span');
                cachedSpan.textContent = ' [Cached]';
                cachedSpan.style.color = '#888';
                cachedSpan.style.fontStyle = 'italic';
                title.appendChild(cachedSpan);
            }
        }

        jobDiv.appendChild(title);

        // Create a non-collapsible table for result, reason, and state
        const resultTable = document.createElement('table');
        const tbody = document.createElement('tbody');
        const resultFields = ['result', 'reason', 'state'];
        resultFields.forEach(field => {
            if (jobDetails[field]) {
                const row = tbody.insertRow();
                const keyCell = row.insertCell();
                keyCell.textContent = field.charAt(0).toUpperCase() + field.slice(1);
                keyCell.className = 'settings-key';
                const valueCell = row.insertCell();
                valueCell.textContent = jobDetails[field];
                valueCell.className = 'settings-value';
            }
        });
        resultTable.appendChild(tbody);
        jobDiv.appendChild(resultTable);

        // Separate specific fields to be collapsible
        const autoinstLog = jobDetails['autoinst-log'];
        const settings = jobDetails['settings'];
        const exceptions = [];

        // Create a copy of jobDetails to show the rest
        const otherDetails = { ...jobDetails };
        delete otherDetails['autoinst-log'];
        delete otherDetails['settings'];
        delete otherDetails['result'];
        delete otherDetails['reason'];
        delete otherDetails['state'];

        // Collect full exception messages and their original index
        if (autoinstLog && Array.isArray(autoinstLog)) {
            autoinstLog.forEach((entry, index) => {
                if (entry.type === 'exception') {
                    exceptions.push({ message: entry.message, log_index: index });
                }
            });
        }
        jobDetails.exceptions = exceptions;

        if (settings) {
            jobDiv.appendChild(_createCollapsibleSection('Settings', settings));
        }

        if (autoinstLog) {
            const logSection = _createCollapsibleSection('autoinst-log', jobDetails, jobId);
            logSection.id = `autoinst-log-${jobId}`;
            jobDiv.appendChild(logSection);
        }

        if (exceptions.length > 0) {
            jobDiv.appendChild(_createCollapsibleSection('Exceptions', jobDetails, jobId));
        }

        // Display the rest of the details in a collapsible section
        jobDiv.appendChild(_createCollapsibleSection('Other Details', otherDetails));

        container.appendChild(jobDiv);
    }
}

/**
 * Shows or hides the floating UI controls.
 * @param {boolean} visible - Whether the controls should be visible.
 */
export function toggleFloatingControls(visible) {
    const floatingControls = document.getElementById('floating-controls');
    if (floatingControls) {
        floatingControls.style.display = visible ? 'block' : 'none';
    }
}

