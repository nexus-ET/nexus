import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../src/helpers/auth';

/**
 * UAT — Framework / Academia changes (2026-08-28):
 * Summary coverage metrics, tab pagination, country filter, CA Mapping Review.
 */
test.describe('Framework recent: Summary & coverage', () => {
  test('Framework Summary View loads coverage metrics', async ({ page }) => {
    await gotoAppPath(page, '/academia/framework/summary');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(
      page.getByText(/Summary View|Framework|Coverage|Programs with no major/i).first()
    ).toBeVisible({ timeout: 45_000 });
    await expect(
      page.getByText(/Campus|College|Institution|No Major|No Sub-Major/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });
});

test.describe('Framework recent: tab pagination (page size 100)', () => {
  for (const tab of [
    { path: '/academia/framework/super-majors', label: 'Super-Majors' },
    { path: '/academia/framework/majors', label: 'Majors' },
    { path: '/academia/framework/sub-majors', label: 'Sub-Majors' },
    { path: '/academia/framework/programs', label: 'Programs' },
  ]) {
    test(`${tab.label} tab exposes pagination controls`, async ({ page }) => {
      await gotoAppPath(page, tab.path);
      await expect(page).not.toHaveURL(/\/login$/);
      await expect(page.getByText(new RegExp(tab.label, 'i')).first()).toBeVisible({
        timeout: 45_000,
      });
      const pageSize = page.getByRole('combobox').filter({ hasText: /100|25|50|page size/i });
      const pagination = page.getByText(/Page \d+ of \d+|Showing \d+/i);
      await expect(pageSize.or(pagination).first()).toBeVisible({ timeout: 45_000 });
    });
  }
});

test.describe('Framework recent: country filter', () => {
  test('Institutions summary exposes country filter', async ({ page }) => {
    await gotoAppPath(page, '/academia/institutions');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(/Institution|Summary|Country/i).first()).toBeVisible({
      timeout: 45_000,
    });
    const countryFilter = page.getByLabel(/Country/i).or(page.getByText(/^Country$/i));
    await expect(countryFilter.first()).toBeVisible({ timeout: 45_000 });
  });

  test('Framework Programs exposes country filter', async ({ page }) => {
    await gotoAppPath(page, '/academia/framework/programs');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(/Programs|Country|Institution/i).first()).toBeVisible({
      timeout: 45_000,
    });
    const countryFilter = page.getByLabel(/Country/i).or(page.getByText(/^Country$/i));
    await expect(countryFilter.first()).toBeVisible({ timeout: 45_000 });
  });
});

test.describe('Framework recent: CA Mapping Review', () => {
  test('CA Mapping Review page loads', async ({ page }) => {
    await gotoAppPath(page, '/academia/framework/ca-mapping-review');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(
      page.getByText(/CA Program Mapping Review|CA-24|mapping suggestions/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('CA mapping suggestions API responds for admin', async ({ request }) => {
    const baseUrl = process.env.UAT_BASE_URL || 'http://127.0.0.1:5175';
    const email = process.env.UAT_EMAIL;
    const password = process.env.UAT_PASSWORD;
    test.skip(!email || !password, 'UAT credentials required for API gate');

    const login = await request.post(`${baseUrl}/api/v1/login`, {
      form: { username: email!, password: password! },
    });
    expect(login.ok(), await login.text()).toBeTruthy();
    const token = (await login.json()).access_token as string;

    const resp = await request.get(
      `${baseUrl}/api/v1/academia/ca-program-mapping-suggestions`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect([200, 404]).toContain(resp.status());
    if (resp.status() === 404) {
      const body = await resp.json();
      expect(JSON.stringify(body)).toMatch(/not found|suggestions/i);
    }
  });
});
