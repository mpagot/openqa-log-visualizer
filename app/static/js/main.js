import { ApiClient } from './apiClient.js';
import * as renderer from './renderer.js';
import { initializeTimeline } from './timelineRenderer.js';

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
const apiClient = new ApiClient();

/**
 * Handles a click on an event circle in the timeline.
 * This function is passed as a callback to the timeline renderer.
 * @param {object} event - The event data associated with the clicked circle.
 */
function handleTimelineEventClick(event) {
    if (highlightedRow) {
        highlightedRow.classList.remove('highlighted-row');
    }

    const targetElement = document.getElementById(`autoinst-log-${event.job_id}`);
    const targetRow = document.getElementById(`log-row-${event.job_id}-${event.log_index}`);

    if (targetElement && targetRow) {
        targetRow.classList.add('highlighted-row');
        highlightedRow = targetRow;
        targetElement.open = true; // Ensure the section is expanded
        setTimeout(() => {
            targetRow.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    }
}

document.getElementById('log-form').addEventListener('submit', function(event) {
    event.preventDefault();
    const logUrl = document.getElementById('log_url').value;
    const ignoreCache = document.getElementById('ignore_cache').checked;

    const elements = {
        jobDetailsContainer: document.getElementById('job-details-container'),
        timelineContainer: document.getElementById('timeline-container'),
        debugLogContent: document.getElementById('debug-log-content')
    };

    // 1. Clear previous results and show loading state
    renderer.clearUI(elements);
    renderer.renderLoading(elements.jobDetailsContainer);
    renderer.toggleFloatingControls(false);

    apiClient.analyze(logUrl, ignoreCache)
    .then(data => {
        // --- DEBUG LOGS for data structure validation ---
        console.group('Backend Data Analysis');

        if (data.error) {
            console.error('Backend returned an error:', data.error);
        }

        if (!data.jobs) {
            console.warn('Data object is missing the "jobs" property.');
        }

        if (!data.timeline_events || data.timeline_events.length === 0) {
            console.warn('Data object has no "timeline_events".');
        }

        if (!data.event_pairs) {
            console.warn('Data object is missing "event_pairs" for arrows.');
        } else {
            console.log(`Received ${data.event_pairs.length} event pairs.`);
        }
        console.groupEnd();
        // --- END DEBUG LOGS ---
        renderer.clearUI(elements); // Clear loading message
        renderer.renderDebugLog(data.debug_log, elements.debugLogContent);

        // Handle timeline visualization
        if (data.timeline_events?.length > 0) {
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
            initializeTimeline(data.timeline_events, data.jobs, 'timeline-container', typeColorMap, data.event_pairs, handleTimelineEventClick);
        } else {
            elements.timelineContainer.innerHTML = '<p>No timeline events to display.</p>';
        }

        // Handle main content (job details or error)
        if (data.error) {
            renderer.renderError(data.error, elements.jobDetailsContainer);
        } else if (data.jobs) {
            areAllExpanded = false;
            toggleBtn.textContent = 'Expand All';
            renderer.toggleFloatingControls(true);
            renderer.renderJobDetails(data.jobs, elements.jobDetailsContainer);
        } else {
            // Fallback for unexpected structure from a 2xx response
            const fallbackMessage = 'Received an unexpected response structure.\n\n' + JSON.stringify(data, null, 2);
            renderer.renderError(fallbackMessage, elements.jobDetailsContainer);
        }
    })
    .catch(error => {
        console.error('Fetch Error:', error);
        renderer.clearUI(elements);
        renderer.renderError(`A client-side error occurred: ${error.message}`, elements.jobDetailsContainer);
        renderer.renderDebugLog([{ level: 'error', message: `[FATAL] ${error.message}. Is the server running? Check the browser console for more details.` }], elements.debugLogContent);
    });
});

// --- Event Delegation for UI interactions ---
const jobDetailsContainer = document.getElementById('job-details-container');

// Handle clicks on log links
jobDetailsContainer.addEventListener('click', function(e) {
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

// Handle collapsing sections to remove highlights
jobDetailsContainer.addEventListener('toggle', (e) => {
    if (e.target.tagName === 'DETAILS' && !e.target.open) {
        if (highlightedRow && e.target.contains(highlightedRow)) {
            highlightedRow.classList.remove('highlighted-row');
            highlightedRow = null;
        }
    }
}, true); // Use capture phase to handle event before it bubbles