import path from 'path';
import { expect, type Page } from '@playwright/test';
import { ensureAuthDir, requireCredentials } from './env';

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
  // Login shell was redesigned (Nexus Intel / FlowX) — heading is no longer "NEXUS Login".
  await expect(page.getByRole('heading', { name: /Sign in to Nexus Intel/i })).toBeVisible();

  await page.locator('input[name="username"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /^Sign In$/i }).click();

  await expect(page).not.toHaveURL(/\/login$/, { timeout: 30_000 });
  await expect(page.locator('body')).not.toContainText(/Invalid email or password|Login failed/i);

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

/** Persist JWT so later Playwright contexts recover after a mid-suite session loss. */
async function persistAuthState(page: Page): Promise<void> {
  const authFile = path.join(ensureAuthDir(), 'user.json');
  await page.context().storageState({ path: authFile });
}

async function isGuestUserChip(page: Page): Promise<boolean> {
  return page.getByRole('button', { name: /Guest User/i }).isVisible().catch(() => false);
}

async function isShellHydrating(page: Page): Promise<boolean> {
  const loadingNav = await page.getByText('Loading navigation...').isVisible().catch(() => false);
  const mainLoading = await page
    .locator('main')
    .getByText(/^Loading…$/)
    .isVisible()
    .catch(() => false);
  return loadingNav || mainLoading;
}

/**
 * Wait until the dashboard shell has a real user (not Guest + stuck Loading).
 * Re-logins when hydration finishes as Guest, JWT was cleared mid-suite, or
 * Guest+Loading hangs past the SPA session-bootstrap budget (avoids 2m test timeouts).
 */
export async function waitForAuthenticatedShell(
  page: Page,
  options?: { timeoutMs?: number }
): Promise<void> {
  // Keep under the Playwright test timeout (120s) so gotoAppPath can retry once.
  const timeoutMs = options?.timeoutMs ?? 50_000;
  const deadline = Date.now() + timeoutMs;
  // Mirrors NexusDashboard SESSION_BOOTSTRAP_TIMEOUT (20s) + quiet retry (~22s) + slack.
  const stuckGuestHydratingBudgetMs = 35_000;
  let guestHydratingSince: number | null = null;

  while (Date.now() < deadline) {
    if (/\/login\/?$/.test(new URL(page.url()).pathname)) {
      await loginViaUi(page);
      await persistAuthState(page);
      guestHydratingSince = null;
      continue;
    }

    const guest = await isGuestUserChip(page);
    const hydrating = await isShellHydrating(page);

    if (!guest && !hydrating) {
      return;
    }

    // Hydration finished as Guest — token missing/invalid or /users/me failed hard.
    if (guest && !hydrating) {
      await loginViaUi(page);
      await persistAuthState(page);
      guestHydratingSince = null;
      continue;
    }

    // Guest + Loading…: bootstrap in flight, or hung (busy API / aborted fetch never settling).
    if (guest && hydrating) {
      if (guestHydratingSince == null) {
        guestHydratingSince = Date.now();
      } else if (Date.now() - guestHydratingSince >= stuckGuestHydratingBudgetMs) {
        await page.evaluate(() => {
          sessionStorage.removeItem('token');
          localStorage.removeItem('token');
        });
        await loginViaUi(page);
        await persistAuthState(page);
        guestHydratingSince = null;
        continue;
      }
    } else {
      guestHydratingSince = null;
    }

    const slice = Math.min(1000, Math.max(0, deadline - Date.now()));
    if (slice <= 0) break;
    await page.waitForTimeout(slice);
  }

  throw new Error(
    `Authenticated shell did not hydrate within ${timeoutMs}ms (Guest User / Loading stuck)`
  );
}

/**
 * Navigate within the authenticated SPA and assert we were not bounced to login.
 * Staging can be slower than local — retry once on navigation timeout.
 * Also recovers from mid-suite session loss (Guest User + stuck Loading… / 401 → /login).
 */
export async function gotoAppPath(page: Page, pathName: string): Promise<void> {
  let lastError: unknown;
  const targetPath = pathName.split('?')[0] || pathName;

  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      await page.goto(pathName, { waitUntil: 'domcontentloaded', timeout: 60_000 });

      // storageState miss, expired JWT, or /users/me 401 → hard redirect to /login.
      // Recover immediately instead of waiting 20s on not.toHaveURL(/login/).
      if (/\/login\/?$/.test(new URL(page.url()).pathname)) {
        await loginViaUi(page);
        await persistAuthState(page);
        await page.goto(pathName, { waitUntil: 'domcontentloaded', timeout: 60_000 });
      }

      await expect(page, `Expected authenticated navigation to ${pathName}`).not.toHaveURL(
        /\/login$/,
        { timeout: 10_000 }
      );
      await waitForAuthenticatedShell(page, { timeoutMs: 50_000 });

      // Re-login may have left us on the post-login landing page.
      if (!page.url().includes(targetPath)) {
        await page.goto(pathName, { waitUntil: 'domcontentloaded', timeout: 60_000 });
        if (/\/login\/?$/.test(new URL(page.url()).pathname)) {
          await loginViaUi(page);
          await persistAuthState(page);
          await page.goto(pathName, { waitUntil: 'domcontentloaded', timeout: 60_000 });
        }
        await expect(page).not.toHaveURL(/\/login$/, { timeout: 10_000 });
        await waitForAuthenticatedShell(page, { timeoutMs: 45_000 });
      }
      return;
    } catch (err) {
      lastError = err;
      if (attempt === 2) break;
      try {
        await loginViaUi(page);
        await persistAuthState(page);
      } catch {
        // Next goto attempt may still recover.
      }
      await page.waitForTimeout(1500);
    }
  }
  throw lastError;
}
