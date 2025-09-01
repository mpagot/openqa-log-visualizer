const floatingControls = document.getElementById('floating-controls');
const toggleBtn = document.getElementById('toggle-all-btn');
const scrollTopBtn = document.getElementById('scroll-top-btn');
let areAllExpanded = false;

toggleBtn.addEventListener('click', () => {
    areAllExpanded = !areAllExpanded;
    document.querySelectorAll('#job-details-container details').forEach(d => d.open = areAllExpanded);
    toggleBtn.textContent = areAllExpanded ? 'Collapse All' : 'Expand All';
});

scrollTopBtn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
});

let highlightedRow = null;
document.getElementById('log-form').addEventListener('submit', function(event) {
    event.preventDefault();
    const logUrl = document.getElementById('log_url').value;
    const ignoreCache = document.getElementById('ignore_cache').checked;
    const jobDetailsContainer = document.getElementById('job-details-container');
    const timelineContainer = document.getElementById('timeline-container');
    const debugLogContent = document.getElementById('debug-log-content');
    const floatingControls = document.getElementById('floating-controls');

    // Clear previous results and show loading message
    jobDetailsContainer.innerHTML = '<pre>Analyzing...</pre>';
    timelineContainer.innerHTML = '';
    debugLogContent.innerHTML = '';

    fetch('/analyze', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ log_url: logUrl, ignore_cache: ignoreCache })
    })
    .then(response => response.json())
    .then(data => {
        jobDetailsContainer.innerHTML = ''; // Clear 'Analyzing...' message

        // Handle debug log first, as it should be present in both success and error responses
        if (data.debug_log && Array.isArray(data.debug_log)) {
            data.debug_log.forEach(log => {
                const logEntry = document.createElement('div');
                logEntry.textContent = `[${log.level.toUpperCase()}] ${log.message}`;
                logEntry.className = `log-${log.level}`; // Assign class for styling
                debugLogContent.appendChild(logEntry);
            });
        }

        // Handle timeline visualization
        if (data.timeline_events && data.timeline_events.length > 0) {
            // Define color palette in the frontend
            const COLOR_PALETTE = [
                '#007bff', '#28a745', '#fd7e14', '#6f42c1', '#dc3545', '#17a2b8',
                '#ffc107', '#6610f2', '#e83e8c', '#20c997', '#6c757d', '#343a40'
            ];

            // Dynamically create the color map from the types provided by the backend
            const typeColorMap = {};
            if (data.event_types) {
                data.event_types.forEach((type, i) => {
                    typeColorMap[type] = COLOR_PALETTE[i % COLOR_PALETTE.length];
                });
            }
            setupTimeline(data.timeline_events, data.jobs, 'timeline-container', typeColorMap);
        } else {
            timelineContainer.innerHTML = '<p>No timeline events to display.</p>';
        }

        // Handle main content (job details or error)
        if (data.error) {
            const errorPre = document.createElement('pre');
            errorPre.textContent = `Error: ${data.error}`;
            jobDetailsContainer.appendChild(errorPre);
        } else if (data.jobs) {
            // Reset state and show floating controls for new results
            areAllExpanded = false;
            const toggleBtn = document.getElementById('toggle-all-btn');
            toggleBtn.textContent = 'Expand All';
            floatingControls.style.display = 'block';

            for (const jobId in data.jobs) {
                const jobDetails = data.jobs[jobId];

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
                    jobDiv.appendChild(createCollapsibleSection('Settings', settings));
                }

                if (autoinstLog) {
                    const logSection = createCollapsibleSection('autoinst-log', jobDetails, jobId);
                    logSection.id = `autoinst-log-${jobId}`;
                    jobDiv.appendChild(logSection);
                }

                if (exceptions.length > 0) {
                    jobDiv.appendChild(createCollapsibleSection('Exceptions', jobDetails, jobId));
                }

                // Display the rest of the details in a collapsible section
                jobDiv.appendChild(createCollapsibleSection('Other Details', otherDetails));

                jobDetailsContainer.appendChild(jobDiv);
            }
        } else {
            // Fallback for unexpected structure from a 2xx response
            const fallbackPre = document.createElement('pre');
            fallbackPre.textContent = 'Received an unexpected response structure.\n\n' + JSON.stringify(data, null, 2);
            jobDetailsContainer.appendChild(fallbackPre);
        }
    })
    .catch(error => {
        console.error('Fetch Error:', error);
        jobDetailsContainer.innerHTML = '<pre>A client-side error occurred. See debug log for details.</pre>';
        const errorEntry = document.createElement('div');
        errorEntry.textContent = `[FATAL] ${error.message}`;
        errorEntry.className = 'log-error';
        debugLogContent.appendChild(errorEntry);
    });
});

document.getElementById('job-details-container').addEventListener('click', function(e) {
    if (e.target.tagName === 'A' && e.target.getAttribute('href')?.startsWith('#')) {
        const targetId = e.target.getAttribute('href').substring(1);
        const targetRow = document.getElementById(targetId);

        if (targetRow) {
            e.preventDefault();

            const parentDetails = targetRow.closest('details');
            if (parentDetails) {
                parentDetails.open = true;
            }

            if (highlightedRow) {
                highlightedRow.classList.remove('highlighted-row');
            }
            targetRow.classList.add('highlighted-row');
            highlightedRow = targetRow;

            setTimeout(() => {
                targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 100);
        }
    }
});

function setupTimeline(allEvents, jobs, containerId, typeColorMap) {
    const container = document.getElementById(containerId);
    const resetButton = document.getElementById('reset-zoom-btn');

    const fullStartTime = new Date(allEvents[0].timestamp).getTime();
    const fullEndTime = new Date(allEvents[allEvents.length - 1].timestamp).getTime();

    let currentStartTime = fullStartTime;
    let currentEndTime = fullEndTime;

    function renderCurrentView() {
        renderTimeline(allEvents, jobs, container, currentStartTime, currentEndTime, typeColorMap);
    }

    resetButton.addEventListener('click', () => {
        currentStartTime = fullStartTime;
        currentEndTime = fullEndTime;
        renderCurrentView();
        resetButton.style.display = 'none';
    });

    let selectionRect = null;
    let startX = 0;
    let isDragging = false;

    container.addEventListener('mousedown', (e) => {
        const svg = container.querySelector('.timeline-svg');
        if (!svg || e.target.tagName.toLowerCase() !== 'svg') return;

        const gRect = svg.querySelector('g').getBoundingClientRect();
        if (e.clientX < gRect.left || e.clientX > gRect.right) {
            return;
        }

        isDragging = true;
        const svgRect = svg.getBoundingClientRect();
        startX = e.clientX - svgRect.left;

        selectionRect = document.createElement('div');
        selectionRect.className = 'timeline-selection';
        selectionRect.style.left = `${startX}px`;
        selectionRect.style.top = `${gRect.top - svgRect.top}px`;
        selectionRect.style.height = `${gRect.height}px`;
        selectionRect.style.width = '0px';
        container.appendChild(selectionRect);
        e.preventDefault();
    });

    container.addEventListener('mousemove', (e) => {
        if (!isDragging || !selectionRect) return;
        const svg = container.querySelector('.timeline-svg');
        const svgRect = svg.getBoundingClientRect();
        const currentX = e.clientX - svgRect.left;
        selectionRect.style.width = `${Math.abs(currentX - startX)}px`;
        selectionRect.style.left = `${Math.min(currentX, startX)}px`;
    });

    container.addEventListener('mouseup', (e) => {
        if (!isDragging) return;
        isDragging = false;

        const svg = container.querySelector('.timeline-svg');
        const svgRect = svg.getBoundingClientRect();
        const endX = e.clientX - svgRect.left;

        if (selectionRect) {
            container.removeChild(selectionRect);
            selectionRect = null;
        }

        if (Math.abs(endX - startX) < 10) return;

        const gTransform = svg.querySelector('g').getAttribute('transform');
        const marginLeft = parseFloat(gTransform.match(/translate\(([\d.]+)/)[1]);
        const marginRight = 50;
        const chartWidth = svgRect.width - marginLeft - marginRight;

        const timeDomain = currentEndTime - currentStartTime;

        const startPos = Math.max(0, Math.min(startX, endX) - marginLeft);
        const endPos = Math.min(chartWidth, Math.max(startX, endX) - marginLeft);

        const newStartTime = currentStartTime + (startPos / chartWidth) * timeDomain;
        const newEndTime = currentStartTime + (endPos / chartWidth) * timeDomain;

        currentStartTime = newStartTime;
        currentEndTime = newEndTime;

        renderCurrentView();
        resetButton.style.display = 'inline-block';
    });

    renderCurrentView();
}

function renderTimeline(allEvents, jobs, container, startTime, endTime, typeColorMap) {
    container.innerHTML = '';

    const getShortName = (jobId) => {
        if (jobs && jobs[jobId] && jobs[jobId].short_name) {
            return jobs[jobId].short_name;
        }
        return jobId; // Fallback to job id if not found
    };

    const events = allEvents.filter(e => {
        const t = new Date(e.timestamp).getTime();
        return t >= startTime && t <= endTime;
    });

    const participants = [...new Set(allEvents.map(e => getShortName(e.job_id)))].sort();
    const margin = { top: 20, right: 50, bottom: 40, left: 120 };
    const width = container.clientWidth - margin.left - margin.right;
    const height = participants.length * 40 + margin.top + margin.bottom;

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute('class', 'timeline-svg');
    svg.setAttribute('width', width + margin.left + margin.right);
    svg.setAttribute('height', height);
    container.appendChild(svg);

    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute('transform', `translate(${margin.left},${margin.top})`);
    svg.appendChild(g);

    // Time scale
    const timeDomain = endTime - startTime;

    const xScale = (timestamp) => {
        const eventTime = new Date(timestamp).getTime();
        if (timeDomain === 0) return width / 2;
        return ((eventTime - startTime) / timeDomain) * width;
    };

    // Participant scale (Y-axis)
    const yScale = (participant) => {
        return participants.indexOf(participant) * 40 + 20;
    };

    // Draw participant labels and lifelines
    participants.forEach(p => {
        const y = yScale(p);
        const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
        label.setAttribute('x', -10);
        label.setAttribute('y', y);
        label.setAttribute('text-anchor', 'end');
        label.setAttribute('dominant-baseline', 'middle');
        label.setAttribute('class', 'timeline-participant-label');
        label.textContent = p;
        g.appendChild(label);

        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute('x1', 0);
        line.setAttribute('x2', width);
        line.setAttribute('y1', y);
        line.setAttribute('y2', y);
        line.setAttribute('stroke', '#ccc');
        line.setAttribute('stroke-dasharray', '2,2');
        g.appendChild(line);
    });

    // Draw time axis
    const timeAxis = document.createElementNS("http://www.w3.org/2000/svg", "g");
    timeAxis.setAttribute('transform', `translate(0, ${height - margin.top - margin.bottom + 10})`);
    g.appendChild(timeAxis);

    const axisLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
    axisLine.setAttribute('x1', 0);
    axisLine.setAttribute('x2', width);
    axisLine.setAttribute('stroke', 'black');
    timeAxis.appendChild(axisLine);

    const startLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
    startLabel.setAttribute('x', 0);
    startLabel.setAttribute('y', 20);
    startLabel.textContent = new Date(startTime).toLocaleTimeString();
    timeAxis.appendChild(startLabel);

    const endLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
    endLabel.setAttribute('x', width);
    endLabel.setAttribute('y', 20);
    endLabel.setAttribute('text-anchor', 'end');
    endLabel.textContent = new Date(endTime).toLocaleTimeString();
    timeAxis.appendChild(endLabel);

    // Tooltip
    const tooltip = document.createElement('div');
    tooltip.className = 'timeline-tooltip';
    container.appendChild(tooltip);

    // Draw events
    events.forEach(event => {
        const x = xScale(event.timestamp);
        const shortName = getShortName(event.job_id);
        const y = yScale(shortName);
        
        const color = (typeColorMap && typeColorMap[event.type]) || '#808080'; // Default to gray for unknown types

        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute('cx', x);
        circle.setAttribute('cy', y);
        circle.setAttribute('r', 5);
        circle.setAttribute('fill', color);
        circle.setAttribute('class', 'timeline-event-marker');
        g.appendChild(circle);

        circle.addEventListener('mouseover', (e) => {
            tooltip.style.opacity = '1';
            tooltip.innerHTML = `<strong>${event.timestamp}</strong><br>${shortName}<br>${cleanLogMessage(event.message)}`;
        });
        circle.addEventListener('mousemove', (e) => {
            const rect = container.getBoundingClientRect();
            tooltip.style.left = `${e.clientX - rect.left + 15}px`;
            tooltip.style.top = `${e.clientY - rect.top + 15}px`;
        });
        circle.addEventListener('mouseout', () => {
            tooltip.style.opacity = '0';
        });

        circle.addEventListener('click', () => {
            if (highlightedRow) {
                highlightedRow.classList.remove('highlighted-row');
            }

            const targetElement = document.getElementById(`autoinst-log-${event.job_id}`);
            const targetRow = document.getElementById(`log-row-${event.job_id}-${event.log_index}`);

            if (targetElement && targetRow) {
                targetRow.classList.add('highlighted-row');
                highlightedRow = targetRow;
                targetElement.open = true; // Ensure the section is expanded
                // Use a timeout to ensure the browser has rendered the expanded
                // section before scrolling to the correct row.
                setTimeout(() => {
                    targetRow.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 100);
            }
        });
    });

    // Add Legend
    const legendContainer = document.getElementById('timeline-legend');
    legendContainer.innerHTML = ''; // Clear previous legend
    
    if (typeColorMap) {
        for (const type in typeColorMap) {
            const legendItem = document.createElement('div');
            legendItem.className = 'legend-item';

            const colorBox = document.createElement('div');
            colorBox.className = 'legend-color';
            colorBox.style.backgroundColor = typeColorMap[type];

            const label = document.createElement('span');
            label.textContent = type.charAt(0).toUpperCase() + type.slice(1);

            legendItem.appendChild(colorBox);
            legendItem.appendChild(label);
            legendContainer.appendChild(legendItem);
        }
    }
}

function cleanLogMessage(message) {
    // Remove ANSI escape codes (e.g., \u001b[37m)
    let cleaned = message.replace(/\u001b\[.*?m/g, '');
    // Remove the log prefix (e.g., [debug] [pid:12345])
    cleaned = cleaned.replace(/^\[\w+\]\s\[pid:\d+\]\s*/, '');
    return cleaned;
}

function createCollapsibleSection(title, data, jobId) {
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
        details.addEventListener('toggle', () => {
            if (!details.open && highlightedRow && details.contains(highlightedRow)) {
                highlightedRow.classList.remove('highlighted-row');
                highlightedRow = null;
            }
        });
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