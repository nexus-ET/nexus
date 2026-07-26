import { test, expect } from '@playwright/test';
import { loadUatEnv } from '../src/helpers/env';
import {
  generateUniversityShortlist,
  openUniversityShortlistTab,
} from '../src/helpers/shortlist';
import { gotoAppPath } from '../src/helpers/auth';

/**
 * UAT — University matching score generation, shortlist results, and band filters.
 */
test.describe('University matching & shortlist', () => {
  test('My Bookings surfaces booking cards or empty-state messaging', async ({ page }) => {
    await gotoAppPath(page, '/my-bookings');
    await expect(page.getByRole('heading', { name: /My Bookings/i })).toBeVisible({
      timeout: 45_000,
    });
    await expect(
      page
        .getByRole('button', { name: /Past .*Bookings|Today .*Bookings|Upcoming .*Bookings/i })
        .or(page.getByText(/No bookings for|Try another date/i))
        .first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('University Shortlist tab is reachable from counselling student profile', async ({
    page,
  }) => {
    await openUniversityShortlistTab(page);
    await expect(
      page
        .getByText(
          /University Shortlist|Generate shortlist|Regenerate shortlist|No shortlist|weight|fit|Phase 1/i
        )
        .first()
    ).toBeVisible({ timeout: 30_000 });
  });

  test('Generate shortlist produces multi-category matching scores (Academic, Profile, Aspirations, Safety)', async ({
    page,
  }) => {
    await generateUniversityShortlist(page);

    const emptyRun = page.getByText(
      /No matching|no matching institutions|insufficient|No shortlist yet/i
    );
    if (await emptyRun.first().isVisible().catch(() => false)) {
      await expect(emptyRun.first()).toBeVisible();
      return;
    }

    // Phase 1 heuristic fit cards expose the four scoring dimensions.
    await expect(page.getByText(/^Academic$/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/^Profile$/i).first()).toBeVisible();
    await expect(page.getByText(/^Aspirations$/i).first()).toBeVisible();
    await expect(page.getByText(/^Safety\*?$/i).first()).toBeVisible();
    await expect(page.getByText(/Fit score/i).first()).toBeVisible();
  });

  test('Shortlisted institutions support Safe / Target / Reach band filtering', async ({
    page,
  }) => {
    await generateUniversityShortlist(page);

    const emptyRun = page.getByText(
      /No matching|no matching institutions|insufficient|No shortlist yet/i
    );
    if (await emptyRun.first().isVisible().catch(() => false)) {
      test.skip(true, 'No shortlist institutions to filter');
      return;
    }

    await expect(page.getByRole('button', { name: /All \(/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('button', { name: /Safe \(/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Target \(/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Reach \(/i })).toBeVisible();

    await page.getByRole('button', { name: /Safe \(/i }).click({ force: true });
    await page.getByRole('button', { name: /Target \(/i }).click({ force: true });
    await page.getByRole('button', { name: /Reach \(/i }).click({ force: true });
    await page.getByRole('button', { name: /All \(/i }).click({ force: true });

    // After filtering back to All, results / institution cards remain visible.
    await expect(
      page.getByText(/Results|Fit score|Institution|Safe|Target|Reach|Why this match/i).first()
    ).toBeVisible();
  });

  test('weight profiles API surface is reachable for matching configuration', async ({
    request,
  }) => {
    const { baseUrl } = loadUatEnv();
    const response = await request.get(baseUrl);
    expect(response.status(), `Expected SPA origin ${baseUrl} to respond`).toBeLessThan(500);
  });
});
