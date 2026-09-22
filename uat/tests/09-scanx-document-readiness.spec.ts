import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../src/helpers/auth';
import { loadUatEnv } from '../src/helpers/env';

/**
 * UAT — ScanX / Document Readiness (Students pipeline stage 3).
 * Smoke only: shell + Upload control. Do not upload a passport or wait on OCR.
 */
test.describe('ScanX / Document Readiness', () => {
  test('Document Readiness pipeline loads ScanX shell', async ({ page }) => {
    await gotoAppPath(page, '/students/document-readiness');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 45_000 });

    await expect(
      page.getByText(/Document Readiness|ScanX|Sub-Process/i).first()
    ).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/^ScanX$/i).first()).toBeVisible({ timeout: 30_000 });
  });

  test('UAT lead Document Readiness shows Upload control without crashing', async ({
    page,
  }) => {
    const { leadId } = loadUatEnv();
    await gotoAppPath(page, `/students/document-readiness/${leadId}`);
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 45_000 });

    // Identity / ScanX chrome — do not wait for OCR or document list completion.
    await expect(
      page.getByText(new RegExp(`CRM lead #${leadId}|Document Readiness|ScanX`, 'i')).first()
    ).toBeVisible({ timeout: 45_000 });

    const uploadBtn = page.getByRole('button', { name: /^Upload$/i });
    await expect(uploadBtn.first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByRole('button', { name: /Upload Instructions/i }).first()).toBeVisible({
      timeout: 30_000,
    });

    // No uncaught crash banner; Upload may be enabled or disabled depending on config.
    await expect(page.getByText(/Unable to load this lead\.|Something went wrong/i)).toHaveCount(0);
  });
});
