import { describe, it, expect, beforeEach } from 'vitest';
import * as renderer from '../../../app/static/js/renderer.js';

describe('renderer', () => {
    let jobDetailsContainer, timelineContainer, debugLogContent, floatingControls;

    beforeEach(() => {
        // Set up a basic DOM structure for each test
        document.body.innerHTML = `
            <div id="job-details-container"></div>
            <div id="timeline-container"></div>
            <pre id="debug-log-content"></pre>
            <div id="floating-controls"></div>
        `;
        jobDetailsContainer = document.getElementById('job-details-container');
        timelineContainer = document.getElementById('timeline-container');
        debugLogContent = document.getElementById('debug-log-content');
        floatingControls = document.getElementById('floating-controls');
    });

    describe('renderLoading', () => {
        it('should display a loading message', () => {
            renderer.renderLoading(jobDetailsContainer);
            expect(jobDetailsContainer.innerHTML).toBe('<pre>Analyzing...</pre>');
        });
    });

    describe('clearUI', () => {
        it('should clear the content of all UI containers', () => {
            const elements = { jobDetailsContainer, timelineContainer, debugLogContent };
            elements.jobDetailsContainer.innerHTML = 'old content';
            elements.timelineContainer.innerHTML = 'old content';
            elements.debugLogContent.innerHTML = 'old content';

            renderer.clearUI(elements);

            expect(elements.jobDetailsContainer.innerHTML).toBe('');
            expect(elements.timelineContainer.innerHTML).toBe('');
            expect(elements.debugLogContent.innerHTML).toBe('');
        });
    });

    describe('renderError', () => {
        it('should display an error message', () => {
            renderer.renderError('Something went wrong', jobDetailsContainer);
            const pre = jobDetailsContainer.querySelector('pre');
            expect(pre).not.toBeNull();
            expect(pre.textContent).toBe('Error: Something went wrong');
        });
    });

    describe('renderDebugLog', () => {
        it('should render nothing for null or non-array logs', () => {
            renderer.renderDebugLog(null, debugLogContent);
            expect(debugLogContent.innerHTML).toBe('');
            renderer.renderDebugLog({}, debugLogContent);
            expect(debugLogContent.innerHTML).toBe('');
        });

        it('should render debug log entries with correct content and classes', () => {
            const logs = [
                { level: 'info', message: 'Starting analysis' },
                { level: 'error', message: 'Failed to fetch' }
            ];
            renderer.renderDebugLog(logs, debugLogContent);

            const divs = debugLogContent.querySelectorAll('div');
            expect(divs.length).toBe(2);
            expect(divs[0].textContent).toBe('[INFO] Starting analysis');
            expect(divs[0].className).toBe('log-info');
            expect(divs[1].textContent).toBe('[ERROR] Failed to fetch');
            expect(divs[1].className).toBe('log-error');
        });
    });

    describe('toggleFloatingControls', () => {
        it('should show controls when visible is true', () => {
            renderer.toggleFloatingControls(true);
            expect(floatingControls.style.display).toBe('block');
        });

        it('should hide controls when visible is false', () => {
            renderer.toggleFloatingControls(false);
            expect(floatingControls.style.display).toBe('none');
        });
    });

    describe('renderJobDetails', () => {
        const mockJobsData = {
            '12345': {
                job_url: 'http://example.com/12345',
                short_name: 'worker-1',
                parser_name: 'multimachine',
                is_cached: true,
                result: 'passed',
                state: 'done',
                settings: {
                    'TEST': 'my-test',
                    'WORKER_CLASS': 'worker'
                },
                'autoinst-log': [
                    { timestamp: '2023-01-01T10:00:00Z', type: 'info', message: 'Starting test' },
                    { timestamp: '2023-01-01T10:01:00Z', type: 'exception', message: 'Something failed at some/file.pm line 42.' },
                    { timestamp: '2023-01-01T10:02:00Z', type: 'mutex', event_name: 'mutex_lock', mutex: 'my-lock' }
                ],
                'optional_columns': ['mutex'],
                exceptions: [
                    { message: 'Full exception details here.\nAnother line.', log_index: 1 }
                ],
                other_detail: 'some other value'
            }
        };

        it('should render a job entry for each job', () => {
            renderer.renderJobDetails(mockJobsData, jobDetailsContainer);
            const jobEntries = jobDetailsContainer.querySelectorAll('.job-entry');
            expect(jobEntries.length).toBe(1);
        });

        it('should render the job header correctly', () => {
            renderer.renderJobDetails(mockJobsData, jobDetailsContainer);
            const title = jobDetailsContainer.querySelector('h3');
            expect(title).not.toBeNull();
            expect(title.textContent).toContain('12345');
            expect(title.textContent).toContain('worker-1');
            expect(title.textContent).toContain('[Parser: multimachine]');
            expect(title.textContent).toContain('[Cached]');
            const link = title.querySelector('a');
            expect(link.href).toBe('http://example.com/12345');
        });

        it('should render the result table', () => {
            renderer.renderJobDetails(mockJobsData, jobDetailsContainer);
            const rows = jobDetailsContainer.querySelectorAll('.job-entry > table tbody tr');
            expect(rows.length).toBe(2); // result and state
            expect(rows[0].textContent).toContain('Result');
            expect(rows[0].textContent).toContain('passed');
            expect(rows[1].textContent).toContain('State');
            expect(rows[1].textContent).toContain('done');
        });

        it('should create collapsible sections', () => {
            renderer.renderJobDetails(mockJobsData, jobDetailsContainer);
            const details = jobDetailsContainer.querySelectorAll('details');
            expect(details.length).toBe(4); // Settings, autoinst-log, Exceptions, Other Details
            const summaries = Array.from(details).map(d => d.querySelector('summary').textContent);
            expect(summaries).toContain('Settings');
            expect(summaries).toContain('autoinst-log');
            expect(summaries).toContain('Exceptions');
            expect(summaries).toContain('Other Details');
        });

        it('should render the autoinst-log table with correct headers and content', () => {
            renderer.renderJobDetails(mockJobsData, jobDetailsContainer);
            const logSection = Array.from(jobDetailsContainer.querySelectorAll('details')).find(d => d.querySelector('summary').textContent === 'autoinst-log');
            expect(logSection).not.toBeNull();
            
            const headers = Array.from(logSection.querySelectorAll('thead th')).map(th => th.textContent);
            expect(headers).toEqual(['Timestamp', 'Type', 'Mutex', 'Message']);

            const rows = logSection.querySelectorAll('tbody tr');
            expect(rows.length).toBe(3);
            expect(rows[0].id).toBe('log-row-12345-0');
            expect(rows[0].textContent).toContain('2023-01-01T10:00:00Z');
            expect(rows[0].textContent).toContain('Starting test');

            // Check exception link
            const exceptionCell = rows[1].querySelector('.col-message');
            expect(exceptionCell).not.toBeNull();
            const link = exceptionCell.querySelector('a');
            expect(link).not.toBeNull();
            expect(link.href).toContain('#exception-row-12345-0');
            expect(link.textContent).toBe('Something failed at some/file.pm line 42.');
        });

        it('should render the exceptions table with back-links', () => {
            renderer.renderJobDetails(mockJobsData, jobDetailsContainer);
            const exceptionsSection = Array.from(jobDetailsContainer.querySelectorAll('details')).find(d => d.querySelector('summary').textContent === 'Exceptions');
            expect(exceptionsSection).not.toBeNull();

            const row = exceptionsSection.querySelector('tbody tr');
            expect(row.id).toBe('exception-row-12345-0');

            const link = row.querySelector('a');
            expect(link).not.toBeNull();
            expect(link.href).toContain('#log-row-12345-1');
            expect(link.textContent).toBe('[Go to log line 2]');

            const pre = row.querySelector('pre');
            expect(pre.textContent).toContain('Full exception details here.');
        });
    });
});

