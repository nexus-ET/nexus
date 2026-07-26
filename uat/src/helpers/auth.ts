import { expect, type Page } from '@playwright/test';
import { requireCredentials } from './env';

/**
 * Perform Nexus OAuth2 form login via the UI.
 *
 * Nexus stores the JWT in sessionStorage (`token`). Playwright's storageState
 * captures cookies + localStorage, not sessionStorage — so after login we mirror
 * the JWT into localStorage. ProtectedRoute's getStoredToken() migrates
 * localStorage → sessionStorage on the next page load.
 */
export async function loginViaUi(page: Page): Promise<void> {
  const { email, password } = requireCredentials();

  await page.goto('/login');
  await expect(page.getByRole('heading', { name: /NEXUS Login/i })).toBeVisible();

  await page.locator('input[name="username"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /Sign in to Nexus/i }).click();

  await expect(page).not.toHaveURL(/\/login$/, { timeout: 30_000 });
  await expect(page.locator('body')).not.toContainText('Invalid email or password');

  await page.waitForFunction(() => Boolean(sessionStorage.getItem('token')), null, {
    timeout: 15_000,
  });

  await page.evaluate(() => {
    const token = sessionStorage.getItem('token');
    if (token) {
      localStorage.setItem('token', token);
    }
  });
}

/**
 * Navigate within the authenticated SPA and assert we were not bounced to login.
 * Staging can be slower than local — retry once on navigation timeout.
 */
export async function gotoAppPath(page: Page, path: string): Promise<void> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 90_000 });
      await expect(page, `Expected authenticated navigation to ${path}`).not.toHaveURL(/\/login$/, {
        timeout: 20_000,
      });
      return;
    } catch (err) {
      lastError = err;
      if (attempt === 2) break;
      await page.waitForTimeout(1500);
    }
  }
  throw lastError;
}
