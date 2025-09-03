import { describe, it, expect, beforeEach, vi } from 'vitest';
import { initializeTimeline } from '/app/static/js/timelineRenderer.js';

// Mock data for testing
const mockEvents = [
    { timestamp: '2023-01-01T10:00:00Z', job_id: '1', type: 'mutex', event_name: 'mutex_create', mutex: 'lock1', log_index: 0, message: 'create lock1' },
    { timestamp: '2023-01-01T10:01:00Z', job_id: '2', type: 'mutex', event_name: 'mutex_lock', mutex: 'lock1', log_index: 0, message: 'lock lock1' },
    { timestamp: '2023-01-01T10:02:00Z', job_id: '2', type: 'mutex', event_name: 'mutex_unlock', mutex: 'lock1', log_index: 1, message: 'unlock lock1' },
    { timestamp: '2023-01-01T10:03:00Z', job_id: '1', type: 'barrier', event_name: 'barrier_create', barrier: 'b1', log_index: 1, message: 'create barrier1' },
    { timestamp: '2023-01-01T10:04:00Z', job_id: '2', type: 'barrier', event_name: 'barrier_wait', barrier: 'b1', log_index: 2, message: 'wait barrier1' }
];

const mockJobs = {
    '1': { short_name: 'worker-1' },
    '2': { short_name: 'worker-2' }
};

const mockTypeColorMap = {
    'mutex': 'blue',
    'barrier': 'green'
};

const mockEventPairs = [
    {
        pair_type: 'mutex_lock_unlock',
        mutex: 'lock1',
        start_event: mockEvents[1],
        end_event: mockEvents[2]
    },
    {
        pair_type: 'barrier_create_wait',
        barrier: 'b1',
        start_event: mockEvents[3],
        end_event: mockEvents[4]
    }
];

describe('timelineRenderer', () => {
    let container;
    let onEventClick;

    beforeEach(() => {
        // Set up a basic DOM structure for each test
        document.body.innerHTML = `
            <div id="timeline-container" style="position: relative; width: 800px;"></div>
            <div id="sync-legend" class="timeline-legend"></div>
            <div id="timeline-legend" class="timeline-legend"></div>
            <button id="reset-zoom-btn"></button>
        `;
        container = document.getElementById('timeline-container');
        onEventClick = vi.fn();

        // JSDOM doesn't have layout, so clientWidth is 0. We need to mock it.
        Object.defineProperty(container, 'clientWidth', { value: 800 });
    });

    it('should initialize and render the basic SVG structure', () => {
        initializeTimeline(mockEvents, mockJobs, 'timeline-container', mockTypeColorMap, mockEventPairs, onEventClick);

        const svg = container.querySelector('svg.timeline-svg');
        expect(svg).not.toBeNull();

        const participants = svg.querySelectorAll('.timeline-participant-label');
        expect(participants.length).toBe(2);
        expect(participants[0].textContent).toBe('worker-1');
        expect(participants[1].textContent).toBe('worker-2');

        const eventMarkers = svg.querySelectorAll('.timeline-event-marker');
        expect(eventMarkers.length).toBe(5);
    });

    it('should render event type and synchronization legends', () => {
        initializeTimeline(mockEvents, mockJobs, 'timeline-container', mockTypeColorMap, mockEventPairs, onEventClick);

        // Test event type legend
        const legendContainer = document.getElementById('timeline-legend');
        const legendItems = legendContainer.querySelectorAll('.legend-item');
        expect(legendItems.length).toBe(2);
        expect(legendContainer.textContent).toContain('Mutex');
        expect(legendContainer.textContent).toContain('Barrier');

        // Test sync legend
        const syncLegendContainer = document.getElementById('sync-legend');
        const syncLegendItems = syncLegendContainer.querySelectorAll('.legend-item');
        expect(syncLegendItems.length).toBe(2);
        expect(syncLegendContainer.textContent).toContain('Barrier Signal');
        expect(syncLegendContainer.textContent).toContain('Critical Section');
    });

    it('should render critical section rectangles and synchronization arrows', () => {
        initializeTimeline(mockEvents, mockJobs, 'timeline-container', mockTypeColorMap, mockEventPairs, onEventClick);
        const svg = container.querySelector('svg.timeline-svg');

        const rects = svg.querySelectorAll('.critical-section-rect');
        expect(rects.length).toBe(1);
        expect(rects[0].dataset.pairName).toBe('lock1');

        const arrows = svg.querySelectorAll('.event-arrow');
        expect(arrows.length).toBe(1);
        expect(arrows[0].dataset.pairName).toBe('b1');
        expect(arrows[0].style.display).toBe('none'); // Initially hidden
    });

    it('should call the onEventClick callback when an event circle is clicked', () => {
        initializeTimeline(mockEvents, mockJobs, 'timeline-container', mockTypeColorMap, mockEventPairs, onEventClick);
        const firstCircle = container.querySelector('.timeline-event-marker');
        
        // Simulate a click
        const clickEvent = new MouseEvent('click', { bubbles: true });
        firstCircle.dispatchEvent(clickEvent);

        expect(onEventClick).toHaveBeenCalledTimes(1);
        expect(onEventClick).toHaveBeenCalledWith(mockEvents[0]);
    });

    it('should show and hide tooltip on mouseover/mouseout of an event circle', () => {
        initializeTimeline(mockEvents, mockJobs, 'timeline-container', mockTypeColorMap, mockEventPairs, onEventClick);
        const circle = container.querySelector('.timeline-event-marker');
        const tooltip = container.querySelector('.timeline-tooltip');

        // Mouseover
        const mouseoverEvent = new MouseEvent('mouseover', { bubbles: true });
        circle.dispatchEvent(mouseoverEvent);
        expect(tooltip.style.opacity).toBe('1');
        expect(tooltip.innerHTML).toContain(mockEvents[0].timestamp);
        expect(tooltip.innerHTML).toContain('create lock1');

        // Mouseout
        const mouseoutEvent = new MouseEvent('mouseout', { bubbles: true });
        circle.dispatchEvent(mouseoutEvent);
        expect(tooltip.style.opacity).toBe('0');
    });

    it('should show tooltip for critical section on mouseover', () => {
        initializeTimeline(mockEvents, mockJobs, 'timeline-container', mockTypeColorMap, mockEventPairs, onEventClick);
        const rect = container.querySelector('.critical-section-rect');
        const tooltip = container.querySelector('.timeline-tooltip');

        // Mouseover
        const mouseoverEvent = new MouseEvent('mouseover', { bubbles: true });
        rect.dispatchEvent(mouseoverEvent);
        expect(tooltip.style.opacity).toBe('1');
        expect(tooltip.innerHTML).toContain('Critical Section: <strong>lock1</strong>');

        // Mouseout
        const mouseoutEvent = new MouseEvent('mouseout', { bubbles: true });
        rect.dispatchEvent(mouseoutEvent);
        expect(tooltip.style.opacity).toBe('0');
    });

    it('should fade other events and show sync visuals on hover', () => {
        initializeTimeline(mockEvents, mockJobs, 'timeline-container', mockTypeColorMap, mockEventPairs, onEventClick);
        const barrierEventCircle = container.querySelector('#event-marker-1-1'); // The barrier create event
        const arrow = container.querySelector('.event-arrow[data-pair-name="b1"]');

        // Before hover
        expect(arrow.style.display).toBe('none');
        expect(container.querySelectorAll('.faded').length).toBe(0);

        // Mouseover
        const mouseoverEvent = new MouseEvent('mouseover', { bubbles: true });
        barrierEventCircle.dispatchEvent(mouseoverEvent);

        // After hover
        expect(arrow.style.display).toBe('block');
        // 3 events are not part of the 'b1' barrier pair
        expect(container.querySelectorAll('.faded').length).toBe(3);

        // Mouseout
        const mouseoutEvent = new MouseEvent('mouseout', { bubbles: true });
        barrierEventCircle.dispatchEvent(mouseoutEvent);
        expect(arrow.style.display).toBe('none');
        expect(container.querySelectorAll('.faded').length).toBe(0);
    });
});