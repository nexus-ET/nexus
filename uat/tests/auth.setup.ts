import { test as setup, expect } from '@playwright/test';
import path from 'path';
import { loginViaUi } from '../src/helpers/auth';
import { ensureAuthDir, requireCredentials } from '../src/helpers/env';

const authFile = path.join(ensureAuthDir(), 'user.json');

setup('authenticate as UAT counsellor / admin', async ({ page }) => {
  requireCredentials();
  await loginViaUi(page);
  await expect(page).not.toHaveURL(/\/login$/);

  // Confirm storageState will include the JWT (localStorage), not only cookies.
  const persisted = await page.evaluate(() => localStorage.getItem('token'));
  expect(persisted, 'JWT must be mirrored to localStorage before saving storageState').toBeTruthy();

  await page.context().storageState({ path: authFile });
});
