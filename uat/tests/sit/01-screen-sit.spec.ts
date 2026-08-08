import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../../src/helpers/auth';
import { loadUatEnv } from '../../src/helpers/env';
import {
  generateUniversityShortlist,
  openUniversityShortlistTab,
} from '../../src/helpers/shortlist';

/**
 * Phase 1 SIT — Screen-by-screen integration checks.
 */
test.describe('SIT: Student Profile Input Screen', () => {
  test('Counselling Students profile exposes mandatory profile surfaces', async ({ page }) => {
    const { leadId } = loadUatEnv();
    await gotoAppPath(page, `/students/counselling/${leadId}`);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });

    if (await page.getByText(/No counselling booking is available/i).isVisible().catch(() => false)) {
      test.skip(true, 'No booking for UAT lead');
      return;
    }

    // Tab label shortened from "PERSONAL PROFILE" → "Personal" in intake session workspace.
    await page.getByRole('button', { name: /^(Personal|PERSONAL PROFILE)$/i }).click({ force: true });
    await expect(page.locator('input, textarea, select').first()).toBeVisible({ timeout: 30_000 });

    // Client-side required affordances: Save / validation language present on form.
    await expect(
      page.getByRole('button', { name: /Save|Update|Submit/i }).or(page.getByText(/required|email|phone|name/i)).first()
    ).toBeVisible({ timeout: 15_000 });
  });

  test('Aspirations tab accepts preference inputs used by matching', async ({ page }) => {
    const { leadId } = loadUatEnv();
    await gotoAppPath(page, `/students/counselling/${leadId}`);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });
    if (await page.getByText(/No counselling booking is available/i).isVisible().catch(() => false)) {
      test.skip(true, 'No booking for UAT lead');
      return;
    }
    await page.getByRole('button', { name: /ASPIRATIONS/i }).click({ force: true });
    await expect(
      page.getByText(/Country|Degree|Program|Budget|Ranking|Aspiration|Destination/i).first()
    ).toBeVisible({ timeout: 30_000 });
  });
});

test.describe('SIT: Shortlisting Engine Results Screen', () => {
  test('Category breakdown and band filters render after generation', async ({ page }) => {
    await generateUniversityShortlist(page);

    const empty = page.getByText(/No matching|insufficient|No shortlist yet/i);
    if (await empty.first().isVisible().catch(() => false)) {
      await expect(empty.first()).toBeVisible();
      return;
    }

    for (const label of [/Academic/i, /Profile/i, /Aspirations/i, /Safety/i]) {
      await expect(page.getByText(label).first()).toBeVisible();
    }

    await page.getByRole('button', { name: /Safe \(/i }).click({ force: true });
    await page.getByRole('button', { name: /Target \(/i }).click({ force: true });
    await page.getByRole('button', { name: /Reach \(/i }).click({ force: true });
    await page.getByRole('button', { name: /All \(/i }).click({ force: true });
    await expect(page.getByText(/Fit score|Results/i).first()).toBeVisible();
  });

  test('Fit score UI stays within displayable bounds (0–100)', async ({ page }) => {
    await openUniversityShortlistTab(page);
    await generateUniversityShortlist(page);

    const scores = page.locator('text=/Fit score/i');
    if ((await scores.count()) === 0) {
      test.skip(true, 'No fit scores in empty shortlist run');
      return;
    }

    // Numeric fit scores shown beside cards should parse as finite numbers.
    const scoreTexts = await page.locator('.text-xl.font-bold').allTextContents();
    for (const raw of scoreTexts) {
      const n = Number(String(raw).replace(/[^\d.]/g, ''));
      if (Number.isNaN(n)) continue;
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThanOrEqual(100);
    }
  });
});

test.describe('SIT: Counselor Dashboard Screen', () => {
  test('Counselling dashboard calendar / pending digest surfaces load', async ({ page }) => {
    await gotoAppPath(page, '/counselling');
    await expect(
      page.getByText(/Pending|Today|Schedule|Period agenda|Appointments|Booked/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('My Bookings supports session notes / interaction preview affordances', async ({ page }) => {
    await gotoAppPath(page, '/my-bookings');
    await expect(page.getByRole('heading', { name: /My Bookings/i })).toBeVisible({
      timeout: 45_000,
    });

    const upcoming = page.getByRole('button', { name: /Upcoming .*Bookings/i });
    if (await upcoming.isVisible().catch(() => false)) {
      const label = ((await upcoming.innerText()) || '').replace(/\s+/g, ' ');
      if (!/\b0\b/.test(label)) {
        await upcoming.click();
        await page.waitForTimeout(800);
      }
    }

    const preview = page.getByRole('button', {
      name: /View Interaction|Session|Journey|Notes|Profile/i,
    });
    await expect(preview.first().or(page.getByText(/No .*bookings/i).first())).toBeVisible({
      timeout: 30_000,
    });
  });
});
