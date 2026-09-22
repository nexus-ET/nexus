import { expect, type Page } from '@playwright/test';
import { gotoAppPath } from './auth';
import { loadUatEnv } from './env';
import { workspaceTab } from './workspaceTabs';

/**
 * Open the UAT lead on Counselling Students and wait until the intake workspace
 * (or the explicit no-booking empty state) is ready.
 *
 * Shell `Loading…` alone is not enough — lead detail + booking lookup can still
 * be in flight, which is what makes PROFILE / Aspirations clicks flake at ~60s.
 */
export async function openCounsellingIntakeWorkspace(page: Page): Promise<'ready' | 'no_booking'> {
  const { leadId } = loadUatEnv();
  await gotoAppPath(page, `/students/counselling/${leadId}`);
  await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });
  await expect(page.getByText(/Loading lead details/i)).toHaveCount(0, { timeout: 60_000 });
  await expect(page.getByText(/Loading student profile/i)).toHaveCount(0, {
    timeout: 45_000,
  });

  const leadFailed = page.getByText(/Unable to load this lead|Failed to fetch/i);
  if (await leadFailed.first().isVisible().catch(() => false)) {
    throw new Error(`Counselling lead ${leadId} failed to load`);
  }

  const noBooking = page.getByText(/No counselling booking is available/i);
  if (await noBooking.isVisible().catch(() => false)) {
    return 'no_booking';
  }

  await expect(
    workspaceTab(page, /SESSION|PROFILE|DISCOVERY|ROI CALCULATOR/i).first(),
    `Expected intake workspace tabs for counselling lead ${leadId}`
  ).toBeVisible({ timeout: 45_000 });

  return 'ready';
}
