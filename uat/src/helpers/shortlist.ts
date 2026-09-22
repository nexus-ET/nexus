import { expect, type Page } from '@playwright/test';
import { gotoAppPath } from './auth';
import { loadUatEnv } from './env';
import { workspaceTab } from './workspaceTabs';

async function waitForShortlistPanelReady(page: Page): Promise<void> {
  await expect(page.getByText(/Loading university shortlist/i)).toHaveCount(0, {
    timeout: 90_000,
  });
}

/**
 * Open the SHORTLIST tab for the UAT lead on Counselling Students.
 * Falls back to My Bookings when no booking is linked on the counselling profile.
 */
export async function openUniversityShortlistTab(page: Page): Promise<void> {
  const { leadId } = loadUatEnv();

  for (let attempt = 1; attempt <= 2; attempt++) {
    await gotoAppPath(page, `/students/counselling/${leadId}`);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });

    // Shell Loading… is gone; still wait for the prospect detail pane (not /^Loading…$/).
    await expect(page.getByText(/Loading lead details/i)).toHaveCount(0, {
      timeout: 60_000,
    });
    await expect(page.getByText(/Loading student profile/i)).toHaveCount(0, {
      timeout: 45_000,
    }).catch(() => undefined);

    const leadFailed = page.getByText(/Unable to load this lead|Failed to fetch/i);
    if (await leadFailed.first().isVisible().catch(() => false)) {
      if (attempt === 2) {
        throw new Error(`Counselling lead ${leadId} failed to load after retry`);
      }
      await page.waitForTimeout(2000);
      continue;
    }

    const noBooking = page.getByText(/No counselling booking is available/i);
    if (await noBooking.isVisible().catch(() => false)) {
      await gotoAppPath(page, '/my-bookings');
      const upcoming = page.getByRole('button', { name: /Upcoming .*Bookings/i });
      if (await upcoming.isVisible().catch(() => false)) {
        await upcoming.click();
      }
      const openProfile = page.getByRole('button', { name: /Profile|Journey|Session/i });
      await expect(
        openProfile.first(),
        'Need a counselling booking on this account to exercise SHORTLIST'
      ).toBeVisible({ timeout: 30_000 });
      await openProfile.first().click();
    }

    const discoveryTab = workspaceTab(page, /^DISCOVERY$/i);
    await expect(
      discoveryTab.first(),
      `Expected DISCOVERY workspace tab for counselling lead ${leadId}`
    ).toBeVisible({ timeout: 45_000 });
    await discoveryTab.first().click({ force: true });

    const shortlistTab = workspaceTab(page, /^Shortlist$/i);
    await expect(shortlistTab.first()).toBeVisible({ timeout: 45_000 });
    await shortlistTab.first().click({ force: true });
    await waitForShortlistPanelReady(page);
    return;
  }
}

/** Generate (or regenerate) a shortlist run and wait for a result signal. */
export async function generateUniversityShortlist(page: Page): Promise<void> {
  await openUniversityShortlistTab(page);

  // Prior UAT cases may already have a run — reuse it to avoid stacking heavy POSTs.
  const existingBands = page.getByRole('button', { name: /Safe \(/i });
  if (await existingBands.isVisible().catch(() => false)) {
    await expect(page.getByRole('button', { name: /All \(/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Target \(/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Reach \(/i })).toBeVisible();
    return;
  }

  const generateBtn = page.getByRole('button', {
    name: /Generate shortlist|Regenerate shortlist/i,
  });
  await expect(generateBtn).toBeVisible({ timeout: 30_000 });
  await generateBtn.scrollIntoViewIfNeeded();
  // Sticky footer / tab rail often intercepts normal clicks in this layout.
  await generateBtn.click({ force: true });

  // Do not treat the pre-click empty copy ("No shortlist yet") as success — wait until
  // generation finishes (Regenerate label, band filters, or an explicit empty-run message).
  const generatingBtn = page.getByRole('button', { name: /Generating/i });
  await expect(generatingBtn.or(page.getByText(/^Generating/i))).toBeVisible({
    timeout: 15_000,
  }).catch(() => undefined);
  await expect(generatingBtn).toHaveCount(0, { timeout: 90_000 });

  await expect(
    page
      .getByRole('button', { name: /Regenerate shortlist/i })
      .or(page.getByRole('button', { name: /Safe \(/i }))
      .or(page.getByText(/Generated \d+|no matching institutions|No matching|insufficient/i))
      .first()
  ).toBeVisible({ timeout: 90_000 });

  await waitForShortlistPanelReady(page);
}
