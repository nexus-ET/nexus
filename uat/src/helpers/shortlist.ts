import { expect, type Page } from '@playwright/test';
import { gotoAppPath } from './auth';
import { loadUatEnv } from './env';

/**
 * Open the SHORTLIST tab for the UAT lead on Counselling Students.
 * Falls back to My Bookings when no booking is linked on the counselling profile.
 */
export async function openUniversityShortlistTab(page: Page): Promise<void> {
  const { leadId } = loadUatEnv();
  await gotoAppPath(page, `/students/counselling/${leadId}`);
  await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });

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

  const shortlistTab = page.getByRole('button', { name: /^SHORTLIST$/i });
  await expect(shortlistTab.first()).toBeVisible({ timeout: 45_000 });
  await shortlistTab.first().click();
}

/** Generate (or regenerate) a shortlist run and wait for a result signal. */
export async function generateUniversityShortlist(page: Page): Promise<void> {
  await openUniversityShortlistTab(page);

  const generateBtn = page.getByRole('button', {
    name: /Generate shortlist|Regenerate shortlist/i,
  });
  await expect(generateBtn).toBeVisible({ timeout: 30_000 });
  await generateBtn.scrollIntoViewIfNeeded();
  // Sticky footer / tab rail often intercepts normal clicks in this layout.
  await generateBtn.click({ force: true });

  await expect(
    page
      .getByText(
        /Generated|Generating|institution|fit|score|No matching|no matching institutions|Shortlist run|weight profile|Phase 1|insufficient|Results|No shortlist/i
      )
      .first()
  ).toBeVisible({ timeout: 60_000 });
}
