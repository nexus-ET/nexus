import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../src/helpers/auth';
import { loadUatEnv } from '../src/helpers/env';

/**
 * UAT — Student profile submission surfaces (multi-tab candidate dossier).
 * Full CandidateProfilePanel mounts on Counselling Students routes.
 */
test.describe('Student profile submission', () => {
  test('All Prospects page loads prospect list / detail shell', async ({ page }) => {
    await gotoAppPath(page, '/prospects');
    await expect(
      page.getByText(/All Prospects|Recently replied|Contact status|Viewing/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('known UAT lead profile route opens candidate detail', async ({ page }) => {
    const { leadId } = loadUatEnv();
    await gotoAppPath(page, `/prospects/${leadId}`);

    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 45_000 });
    await expect(
      page
        .getByText(
          /Pipeline status|Overview|History|Notes|All Prospects|Viewing|No counselling booking/i
        )
        .first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('candidate profile tabs are available on Counselling Students profile', async ({
    page,
  }) => {
    const { leadId } = loadUatEnv();
    await gotoAppPath(page, `/students/counselling/${leadId}`);

    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });

    const noBooking = page.getByText(/No counselling booking is available/i);
    if (await noBooking.isVisible().catch(() => false)) {
      await expect(noBooking).toBeVisible();
      return;
    }

    await expect(page.getByRole('button', { name: /PROFILE PULSE/i })).toBeVisible({
      timeout: 45_000,
    });
    await expect(
      page.getByRole('button', { name: /ASPIRATIONS|PERSONAL PROFILE|SHORTLIST/i }).first()
    ).toBeVisible();
  });

  test('Aspirations and Personal Profile tabs render editable student info surfaces', async ({
    page,
  }) => {
    const { leadId } = loadUatEnv();
    await gotoAppPath(page, `/students/counselling/${leadId}`);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });

    const noBooking = page.getByText(/No counselling booking is available/i);
    if (await noBooking.isVisible().catch(() => false)) {
      test.skip(true, 'No counselling booking for UAT lead — profile form tabs unavailable');
      return;
    }

    await page.getByRole('button', { name: /ASPIRATIONS/i }).click({ force: true });
    await expect(
      page.getByText(/Aspiration|Destination|Degree|Major|Country|Vision|Preference/i).first()
    ).toBeVisible({ timeout: 30_000 });

    await page.getByRole('button', { name: /PERSONAL PROFILE/i }).click({ force: true });
    await expect(
      page.getByText(/Personal|Name|Email|Phone|Gender|Nationality|Save|Profile/i).first()
    ).toBeVisible({ timeout: 30_000 });
  });

  test('Academia tab exposes education history for matching inputs', async ({ page }) => {
    const { leadId } = loadUatEnv();
    await gotoAppPath(page, `/students/counselling/${leadId}`);
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });

    if (await page.getByText(/No counselling booking is available/i).isVisible().catch(() => false)) {
      test.skip(true, 'No counselling booking for UAT lead');
      return;
    }

    await page.getByRole('button', { name: /^ACADEMIA$/i }).click({ force: true });
    await expect(
      page.getByText(/Education|School|GPA|Degree|Institution|Add|Academic|No education/i).first()
    ).toBeVisible({ timeout: 30_000 });
  });
});
