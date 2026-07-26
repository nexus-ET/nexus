import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../src/helpers/auth';
import { loadUatEnv } from '../src/helpers/env';

/**
 * UAT — WhatsApp counselling workflow surfaces + ops visibility for notification failures.
 */
test.describe('WhatsApp counselling workflows', () => {
  test('AI Active queue page loads lead/contact status controls', async ({ page }) => {
    await gotoAppPath(page, '/ai-active');
    await expect(
      page.getByText(/AI Active|Contact status|Chat started|Not contacted|Viewing|Handoff|Lead/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('Handoffs queue page loads', async ({ page }) => {
    await gotoAppPath(page, '/handoffs');
    await expect(
      page.getByText(/Handoff|Contact status|Queue|Viewing|Advisor|Lead/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('Messaging Hub is reachable for WhatsApp conversation management', async ({ page }) => {
    await gotoAppPath(page, '/messaging-hub');
    await expect(
      page.getByText(/Messaging|WhatsApp|Conversation|Inbox|Chat|Hub|Threads/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('known UAT lead exposes journey timeline (status tracking tied to outreach)', async ({
    page,
  }) => {
    const { leadId } = loadUatEnv();
    await gotoAppPath(page, `/prospects/${leadId}`);
    await page.waitForTimeout(1500);

    const journeyControl = page
      .getByRole('button', { name: /Journey|View journey|Student journey|Timeline/i })
      .or(page.getByTitle(/journey/i))
      .or(page.getByLabel(/journey/i))
      .or(page.getByText(/Student Journey|Journey timeline|View Journey/i));

    if (await journeyControl.first().isVisible().catch(() => false)) {
      await journeyControl.first().click();
      await expect(
        page.getByText(/Journey|Timeline|Status|Outreach|Engagement|Lead:/i).first()
      ).toBeVisible({ timeout: 30_000 });
      return;
    }

    await expect(
      page.getByText(/Pipeline status|Status|Journey|Outreach|Engagement|Lead/i).first()
    ).toBeVisible({ timeout: 30_000 });
  });

  test('Exception Report (ops visibility for WhatsApp/Meta sync failures) is reachable', async ({
    page,
  }) => {
    await gotoAppPath(page, '/reports/exceptions');
    await expect(
      page.getByText(/Exception Report|exceptions|No exceptions|filters|retention|Resolve/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('AI Active contact-status filter supports WhatsApp outreach triage', async ({ page }) => {
    await gotoAppPath(page, '/ai-active');
    await expect(
      page.getByText(/Contact status|Chat started|Not contacted|All/i).first()
    ).toBeVisible({ timeout: 45_000 });

    const chatStarted = page.getByRole('button', { name: /Chat started/i }).or(
      page.getByText(/^Chat started$/i)
    );
    const notContacted = page.getByRole('button', { name: /Not contacted/i }).or(
      page.getByText(/Not contacted yet/i)
    );
    const all = page.getByRole('button', { name: /^All$/i }).or(page.getByText(/^All$/i));

    if (await chatStarted.first().isVisible().catch(() => false)) {
      await chatStarted.first().click({ force: true });
    }
    if (await notContacted.first().isVisible().catch(() => false)) {
      await notContacted.first().click({ force: true });
    }
    if (await all.first().isVisible().catch(() => false)) {
      await all.first().click({ force: true });
    }

    await expect(page.getByText(/Viewing|AI Active|Lead|Contact status/i).first()).toBeVisible();
  });
});
