/**
 * @module timelineRenderer
 * @description
 * This module is responsible for all logic related to creating, rendering,
 * and managing the interactive SVG timeline. It is designed to be self-contained
 * and communicates with the main application via callbacks.
 *
 * Responsibilities:
 * - Creating the main SVG canvas.
 * - Calculating scales (x and y axes).
 * - Drawing lifelines, event circles, and legends.
 * - Handling all interactive features of the timeline: tooltips, hover-to-trace, and click-to-highlight.
 * - Managing its own state for zooming and panning.
 */

/**
 * Renders the synchronization legend (arrows and rectangles).
 * @param {Array} eventPairs - The array of event pairs.
 * @param {Object} typeColorMap - A map of event types to colors.
 */
function _renderSynchronizationLegend(eventPairs, typeColorMap) {
    const legendContainer = document.getElementById('sync-legend');
    if (!legendContainer) return;
    legendContainer.innerHTML = ''; // Clear previous legend

    const hasMutexSignal = eventPairs.some(p => p.pair_type === 'mutex_create_unlock');
    const hasBarrierSignal = eventPairs.some(p => p.pair_type === 'barrier_create_wait');
    const hasLock = eventPairs.some(p => p.pair_type === 'mutex_lock_unlock');

    const legendItems = [];

    if (hasMutexSignal) {
        const color = typeColorMap['mutex'] || '#333';
        legendItems.push({
            symbol: `<svg width="30" height="10"><line x1="0" y1="5" x2="30" y2="5" class="event-arrow" style="stroke: ${color}; stroke-width: 1.5;" marker-end="url(#arrowhead)"></line></svg>`,
            label: 'Mutex Signal'
        });
    }

    if (hasBarrierSignal) {
        const color = typeColorMap['barrier'] || '#333';
        legendItems.push({
            symbol: `<svg width="30" height="10"><line x1="0" y1="5" x2="30" y2="5" class="event-arrow" style="stroke: ${color}; stroke-width: 1.5;" marker-end="url(#arrowhead)"></line></svg>`,
            label: 'Barrier Signal'
        });
    }

    if (hasLock) {
        legendItems.push({
            symbol: '<svg width="30" height="10"><rect x="0" y="0" width="30" height="10" class="critical-section-rect" style="opacity: 0.4;"></rect></svg>',
            label: 'Critical Section'
        });
    }

    if (legendItems.length > 0) {
        legendItems.forEach(item => {
            const legendItem = document.createElement('div');
            legendItem.className = 'legend-item';
            legendItem.innerHTML = `
                <div class="legend-symbol">${item.symbol}</div>
                <span>${item.label}</span>
            `;
            legendContainer.appendChild(legendItem);
        });
    }
}

/**
 * Cleans a log message for display in a tooltip.
 * @param {string} message - The raw log message.
 * @returns {string} The cleaned message.
 */
function _cleanLogMessage(message) {
    // Remove ANSI escape codes (e.g., \u001b[37m)
    let cleaned = message.replace(/\u001b\[.*?m/g, '');
    // Remove the log prefix (e.g., [debug] [pid:12345])
    cleaned = cleaned.replace(/^\[\w+\]\s\[pid:\d+\]\s*/, '');
    return cleaned;
}

/**
 * Renders the main timeline SVG.
 * @param {Array} allEvents - All events for the timeline.
 * @param {Object} jobs - The job details object.
 * @param {HTMLElement} container - The container element for the timeline.
 * @param {number} startTime - The start time for the current view.
 * @param {number} endTime - The end time for the current view.
 * @param {Object} typeColorMap - A map of event types to colors.
 * @param {Array} eventPairs - The array of event pairs for synchronization visuals.
 * @param {function} onEventClick - Callback function for when an event circle is clicked.
 */
function _renderTimeline(allEvents, jobs, container, startTime, endTime, typeColorMap, eventPairs, onEventClick) {
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

    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    defs.innerHTML = `
        <marker id="arrowhead" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#333"></path>
        </marker>
    `;
    svg.appendChild(defs);

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

    // Create a layer for arrows, so we can easily hide/show them all
    const arrowLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
    arrowLayer.setAttribute('class', 'arrow-layer');
    g.appendChild(arrowLayer);

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
        circle.id = `event-marker-${event.job_id}-${event.log_index}`;
        circle.dataset.eventData = JSON.stringify(event);
        g.appendChild(circle);

        circle.addEventListener('mouseover', (e) => {
            tooltip.style.opacity = '1';
            tooltip.innerHTML = `<strong>${event.timestamp}</strong><br>${shortName}<br>${_cleanLogMessage(event.message)}`;

            // Hover-to-Trace logic
            const eventData = JSON.parse(e.target.dataset.eventData);
            const pairName = eventData.mutex || eventData.barrier;

            if (pairName) {

                // Fade unrelated events
                g.querySelectorAll('.timeline-event-marker').forEach(c => {
                    const cData = JSON.parse(c.dataset.eventData);
                    const cPairName = cData.mutex || cData.barrier;
                    if (cPairName !== pairName) {
                        c.classList.add('faded');
                    }
                });

                // --- DEBUG LOGS for hover interaction ---
                console.group(`Hover Trace for: ${pairName}`);
                const arrowSelector = `.event-arrow[data-pair-name="${pairName}"]`;
                const arrows = arrowLayer.querySelectorAll(arrowSelector);
                console.log(`Found ${arrows.length} arrows to show.`);
                arrows.forEach(arrow => {
                    arrow.style.display = 'block';
                });

                const rectSelector = `.critical-section-rect[data-pair-name="${pairName}"]`;
                const rects = g.querySelectorAll(rectSelector);
                console.log(`Found ${rects.length} critical section rectangles to highlight.`);
                rects.forEach(rect => rect.style.opacity = 0.4);
                console.groupEnd();

                // Show the sync legend
                const syncLegend = document.getElementById('sync-legend');
                if (syncLegend) {
                    syncLegend.style.display = 'flex';
                }
            }
        });
        circle.addEventListener('mousemove', (e) => {
            const rect = container.getBoundingClientRect();
            tooltip.style.left = `${e.clientX - rect.left + 15}px`;
            tooltip.style.top = `${e.clientY - rect.top + 15}px`;
        });
        circle.addEventListener('mouseout', (e) => {
            // If the mouse is moving to a critical section rectangle, don't hide the tooltip,
            // let the rectangle's mouseover event handle it. Otherwise, hide it.
            if (!e.relatedTarget || !e.relatedTarget.classList.contains('critical-section-rect')) {
                tooltip.style.opacity = '0';
            }

            // Reset all fades and hide all arrows
            g.querySelectorAll('.timeline-event-marker.faded').forEach(c => c.classList.remove('faded'));
            arrowLayer.querySelectorAll('.event-arrow').forEach(a => {
                a.style.display = 'none';
            });
            g.querySelectorAll('.critical-section-rect').forEach(r => {
                r.style.opacity = 0.15; // Reset to default opacity
            });

            const syncLegend = document.getElementById('sync-legend');
            if (syncLegend) {
                syncLegend.style.display = 'none';
            }
        });

        circle.addEventListener('click', () => {
            onEventClick(event);
        });
    });

    // Draw mutex arrows (initially hidden)
    if (Array.isArray(eventPairs) && eventPairs.length > 0) {
        console.groupCollapsed('Synchronization Rendering'); // Keep this group for debugging
        console.log(`Processing ${eventPairs.length} event pairs.`);
        eventPairs.forEach((pair, index) => {
            const startEvent = pair.start_event;
            const endEvent = pair.end_event;

            const x1 = xScale(startEvent.timestamp);
            const y1 = yScale(getShortName(startEvent.job_id));
            const x2 = xScale(endEvent.timestamp);
            const y2 = yScale(getShortName(endEvent.job_id));

            if (!isNaN(y1) && !isNaN(y2)) {
                if (pair.pair_type === 'mutex_lock_unlock') {
                    const addTooltipHandlersToRect = (element, mutexName) => {
                        element.addEventListener('mouseover', (e) => {
                            tooltip.style.opacity = '1';
                            tooltip.innerHTML = `Critical Section: <strong>${mutexName}</strong>`;
                        });
                        element.addEventListener('mousemove', (e) => {
                            const rect = container.getBoundingClientRect();
                            tooltip.style.left = `${e.clientX - rect.left + 15}px`;
                            tooltip.style.top = `${e.clientY - rect.top + 15}px`;
                        });
                        element.addEventListener('mouseout', (e) => {
                            tooltip.style.opacity = '0';
                        });
                    };

                    // For lock/unlock, always draw rectangles to show the duration of the lock.
                    const rect1 = document.createElementNS("http://www.w3.org/2000/svg", "rect");
                    rect1.setAttribute('x', x1);
                    rect1.setAttribute('y', y1 - 10);
                    rect1.setAttribute('width', x2 - x1);
                    rect1.setAttribute('height', 20);
                    rect1.setAttribute('class', 'critical-section-rect');
                    rect1.setAttribute('data-pair-name', pair.mutex);
                    g.insertBefore(rect1, arrowLayer);
                    addTooltipHandlersToRect(rect1, pair.mutex);

                    if (startEvent.job_id !== endEvent.job_id) {
                        // If it's a cross-job lock, draw a second rectangle on the other lifeline.
                        const rect2 = document.createElementNS("http://www.w3.org/2000/svg", "rect");
                        rect2.setAttribute('x', x1);
                        rect2.setAttribute('y', y2 - 10);
                        rect2.setAttribute('width', x2 - x1);
                        rect2.setAttribute('height', 20);
                        rect2.setAttribute('class', 'critical-section-rect');
                        rect2.setAttribute('data-pair-name', pair.mutex);
                        g.insertBefore(rect2, arrowLayer);
                        addTooltipHandlersToRect(rect2, pair.mutex);
                    }
                } else {
                    // Draw an arrow for all other synchronization types (create/unlock, barrier/wait)
                    const arrow = document.createElementNS("http://www.w3.org/2000/svg", "line");
                    arrow.setAttribute('x1', x1);
                    arrow.setAttribute('y1', y1);
                    arrow.setAttribute('x2', x2);
                    arrow.setAttribute('y2', y2);

                    const eventType = pair.mutex ? 'mutex' : 'barrier';
                    const color = typeColorMap[eventType] || '#333';
                    arrow.setAttribute('stroke', color);

                    arrow.setAttribute('class', 'event-arrow');
                    arrow.setAttribute('data-pair-name', pair.mutex || pair.barrier);
                    arrow.setAttribute('marker-end', 'url(#arrowhead)');
                    arrow.style.display = 'none'; // Hide by default
                    arrowLayer.appendChild(arrow);
                }
            } else {
                // This can happen if a job has no events within the current timeline view,
                // so its lifeline (and thus its y-coordinate) doesn't exist.
                console.warn(`Skipping pair #${index} because one or both lifelines are not in the current view.`, pair);
            }
        });
        console.groupEnd();
    }

    // Add Legend
    _renderSynchronizationLegend(eventPairs, typeColorMap);
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

/**
 * Initializes the timeline, setting up zoom/pan controls and performing the initial render.
 * @param {Array} allEvents - All events for the timeline.
 * @param {Object} jobs - The job details object.
 * @param {string} containerId - The ID of the container element for the timeline.
 * @param {Object} typeColorMap - A map of event types to colors.
 * @param {Array} eventPairs - The array of event pairs for synchronization visuals.
 * @param {function} onEventClick - Callback function for when an event circle is clicked.
 */
export function initializeTimeline(allEvents, jobs, containerId, typeColorMap, eventPairs, onEventClick) {
    const container = document.getElementById(containerId);
    const resetButton = document.getElementById('reset-zoom-btn');

    const fullStartTime = new Date(allEvents[0].timestamp).getTime();
    const fullEndTime = new Date(allEvents[allEvents.length - 1].timestamp).getTime();

    let currentStartTime = fullStartTime;
    let currentEndTime = fullEndTime;

    function renderCurrentView() {
        _renderTimeline(allEvents, jobs, container, currentStartTime, currentEndTime, typeColorMap, eventPairs, onEventClick);
    }

    resetButton.addEventListener('click', () => {
        currentStartTime = fullStartTime;
        currentEndTime = fullEndTime;
        renderCurrentView();
        resetButton.style.display = 'none';
    });

    // --- Robust Drag-to-Zoom Implementation ---
    let selectionRect = null;
    let startX = 0;
    let isDragging = false;

    function onMouseDown(e) {
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

        // Attach move and up listeners to the document to capture events globally
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }

    function onMouseMove(e) {
        if (!isDragging || !selectionRect) return;
        const svg = container.querySelector('.timeline-svg');
        const svgRect = svg.getBoundingClientRect();
        const currentX = e.clientX - svgRect.left;
        selectionRect.style.width = `${Math.abs(currentX - startX)}px`;
        selectionRect.style.left = `${Math.min(currentX, startX)}px`;
    }

    function onMouseUp(e) {
        if (!isDragging) return;
        isDragging = false;

        // Clean up global listeners
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);

        if (selectionRect) {
            container.removeChild(selectionRect);
            selectionRect = null;
        }

        const svg = container.querySelector('.timeline-svg');
        if (!svg) return;
        const svgRect = svg.getBoundingClientRect();
        const endX = e.clientX - svgRect.left;

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
    }

    container.addEventListener('mousedown', onMouseDown);
    renderCurrentView();
}

