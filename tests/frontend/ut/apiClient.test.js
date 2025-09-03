import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from '/app/static/js/apiClient.js';

describe('ApiClient', () => {
    beforeEach(() => {
        // Mock the global fetch function before each test
        global.fetch = vi.fn();
    });

    afterEach(() => {
        // Restore all mocks after each test
        vi.restoreAllMocks();
    });

    it('should send a correct analysis request and return data on success', async () => {
        const mockData = { success: true, jobs: [] };
        global.fetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve(mockData),
        });

        const apiClient = new ApiClient();
        const logUrl = 'http://example.com/123';
        const ignoreCache = false;

        const data = await apiClient.analyze(logUrl, ignoreCache);

        expect(global.fetch).toHaveBeenCalledWith('/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ log_url: logUrl, ignore_cache: ignoreCache }),
        });
        expect(data).toEqual(mockData);
    });

    it('should throw an error with the backend message on a non-ok response', async () => {
        const errorResponse = { error: 'Invalid URL provided' };
        global.fetch.mockResolvedValue({
            ok: false,
            status: 400,
            json: () => Promise.resolve(errorResponse),
        });

        const apiClient = new ApiClient();
        await expect(apiClient.analyze('invalid-url', false)).rejects.toThrow('Invalid URL provided');
    });

    it('should throw a generic error on a network failure', async () => {
        global.fetch.mockRejectedValue(new TypeError('Network request failed'));

        const apiClient = new ApiClient();
        await expect(apiClient.analyze('http://example.com/123', false)).rejects.toThrow('Network request failed');
    });
});