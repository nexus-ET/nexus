import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../src/helpers/auth';

/**
 * UAT — All Leads (offline/express/meta), lead status filter, counselor follow-up notes.
 * Primary nav surfaces added after the original suite; keep assertions landmark-level.
 */
test.describe('All Leads & counselor follow-ups', () => {
  test('All Leads page loads list shell with search and status filter', async ({ page }) => {
    await gotoAppPath(page, '/offline-leads');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 45_000 });

    await expect(page.getByRole('heading', { name: /^All Leads$/i })).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.getByLabel(/Search offline leads/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel(/^Status$/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('button', { name: /Add New Lead/i })).toBeVisible({
      timeout: 30_000,
    });
  });

  test('All Leads status filter exposes Active / Offline / Handoff options', async ({
    page,
  }) => {
    await gotoAppPath(page, '/offline-leads');
    await expect(page.getByRole('heading', { name: /^All Leads$/i })).toBeVisible({
      timeout: 45_000,
    });

    const statusFilter = page.getByLabel(/^Status$/i);
    await expect(statusFilter).toBeVisible({ timeout: 30_000 });
    await expect(statusFilter.locator('option', { hasText: /Active Lead/i })).toHaveCount(1);
    await expect(statusFilter.locator('option', { hasText: /Offline Leads/i })).toHaveCount(1);
    await expect(statusFilter.locator('option', { hasText: /Handoff/i })).toHaveCount(1);
  });

  test('Counselor Notes follow-up drawer opens from All Leads Notes control', async ({
    page,
  }) => {
    await gotoAppPath(page, '/offline-leads');
    await expect(page.getByRole('heading', { name: /^All Leads$/i })).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.getByText(/Loading offline leads/i)).toHaveCount(0, { timeout: 45_000 });

    const empty = page.getByText(/No offline leads match your filters/i);
    if (await empty.isVisible().catch(() => false)) {
      test.skip(true, 'No All Leads rows available to open Counselor Notes');
      return;
    }

    const notesBtn = page.getByRole('button', { name: /Notes/i }).first();
    await expect(notesBtn).toBeVisible({ timeout: 45_000 });
    await notesBtn.click();

    await expect(page.getByText(/^Counselor Notes$/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel(/Follow-up Status/i)).toBeVisible({ timeout: 30_000 });
  });

  test('All Leads table exposes Lead Status column', async ({ page }) => {
    await gotoAppPath(page, '/offline-leads');
    await expect(page.getByRole('heading', { name: /^All Leads$/i })).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.getByText(/Loading offline leads/i)).toHaveCount(0, { timeout: 45_000 });

    const header = page.getByRole('columnheader', { name: /Lead Status/i });
    const empty = page.getByText(/No offline leads match your filters/i);
    if (
      (await empty.isVisible().catch(() => false)) &&
      !(await header.isVisible().catch(() => false))
    ) {
      test.skip(true, 'No All Leads rows and Lead Status header not rendered');
      return;
    }

    await expect(header).toBeVisible({ timeout: 30_000 });
  });

  test('Add New Lead opens Express Leads capture form', async ({ page }) => {
    await gotoAppPath(page, '/offline-leads');
    await expect(page.getByRole('heading', { name: /^All Leads$/i })).toBeVisible({
      timeout: 45_000,
    });

    await page.getByRole('button', { name: /Add New Lead/i }).click();
    await expect(page).toHaveURL(/\/express-leads/, { timeout: 30_000 });
    await expect(
      page
        .getByRole('heading', { name: /Express Leads/i })
        .or(page.getByText(/walk-in|phone enquiry|first name/i).first())
        .first()
    ).toBeVisible({ timeout: 45_000 });
  });
});

test.describe('Students pipeline: College Finding', () => {
  test('College Finding pipeline page loads prospect shell', async ({ page }) => {
    await gotoAppPath(page, '/students/college-finding');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 45_000 });
    await expect(
      page
        .getByText(/College Finding|Recently replied|Contact status|Viewing|All Prospects|Prospect/i)
        .first()
    ).toBeVisible({ timeout: 45_000 });
  });
});
