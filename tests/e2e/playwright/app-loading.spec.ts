import { test, expect } from '@playwright/test';

test('Core Application Loading', async ({ page }) => {
  await page.goto('/');

  // Assert that the main heading is visible
  await expect(page.getByRole('heading', { name: 'openQA Log Analyzer' })).toBeVisible();

  // Assert that the URL input form is visible
  await expect(page.getByLabel('Log URL:')).toBeVisible();

  // Assert that the "Analyze" button is visible
  await expect(page.getByRole('button', { name: 'Analyze' })).toBeVisible();
});
