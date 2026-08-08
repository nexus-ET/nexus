import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../src/helpers/auth';

/**
 * UAT — Authentication shell & session persistence.
 */
test.describe('Auth & shell access', () => {
  test('authenticated session reaches dashboard shell (not login)', async ({ page }) => {
    await gotoAppPath(page, '/');
    await expect(page.locator('body')).toBeVisible();
    // Shell should show app chrome, not the login card.
    await expect(page.getByRole('heading', { name: /Sign in to Nexus Intel|NEXUS Login/i })).toHaveCount(0);
  });

  test('AI Active route is reachable under authenticated session', async ({ page }) => {
    await gotoAppPath(page, '/ai-active');
    await expect(
      page.getByText(/AI Active|Contact status|Chat started|Not contacted|Viewing|Lead/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('My Bookings route is reachable under authenticated session', async ({ page }) => {
    await gotoAppPath(page, '/my-bookings');
    await expect(
      page.getByText(/Past bookings|Today's bookings|Upcoming bookings|My Bookings|Bookings/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });
});
