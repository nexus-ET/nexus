import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../src/helpers/auth';
import { loadUatEnv } from '../src/helpers/env';
import { workspaceTab } from '../src/helpers/workspaceTabs';

/**
 * UAT — New modules / pages added after the baseline 32-case suite:
 * IntelX, FlowX, Book Appointment, Session workspace (Aspirations, Future Insights, ROI).
 */
test.describe('New modules: IntelX', () => {
  test('IntelX Knowledge Hub loads', async ({ page }) => {
    await gotoAppPath(page, '/nexus-intel/knowledge');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(
      page.getByText(/IntelX|Knowledge Hub|Glossary|Terminology|Knowledge/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('IntelX AI Assistant page loads', async ({ page }) => {
    await gotoAppPath(page, '/nexus-intel/ai-assistant');
    await expect(
      page.getByText(/AI Assistant|IntelX|Ask|Chat|Assistant|Knowledge/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('IntelX Workflows page loads', async ({ page }) => {
    await gotoAppPath(page, '/nexus-intel/workflows');
    await expect(
      page.getByText(/Workflows|Proof of funds|Country|IntelX|Comparison/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });
});

test.describe('New modules: FlowX', () => {
  test('FlowX Ops Dashboard loads', async ({ page }) => {
    await gotoAppPath(page, '/flowx/ops');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(
      page.getByText(/FlowX|Ops Dashboard|Operate|Country|Journey|Enrollment/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('FlowX /journeys redirects to ops (list moved to session Applications tab)', async ({
    page,
  }) => {
    await gotoAppPath(page, '/flowx/journeys');
    await expect(page).toHaveURL(/\/flowx\/ops\/?$/, { timeout: 45_000 });
    await expect(page.getByText(/FlowX|Ops Dashboard|Operate/i).first()).toBeVisible({
      timeout: 45_000,
    });
  });

  test('FlowX Country Workflows page loads', async ({ page }) => {
    await gotoAppPath(page, '/flowx/countries');
    await expect(
      page.getByText(/Country Workflows|Countries|FlowX|Master|Configure/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('FlowX Master Workflow page loads', async ({ page }) => {
    await gotoAppPath(page, '/flowx/master');
    await expect(
      page.getByText(/Master Workflow|FlowX|Pathway|Brick|Template|Configure/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });
});

test.describe('New modules: Book Appointment', () => {
  test('Book Appointment page renders staff booking form', async ({ page }) => {
    await gotoAppPath(page, '/book-appointment');
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(/Book Appointment/i).first()).toBeVisible({ timeout: 45_000 });
    await expect(
      page.getByText(/Session purpose|Counsellor|Existing|New candidate|calendar|Availability/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });
});

test.describe('New modules: Intake Session workspace', () => {
  async function openUatLeadSession(page: import('@playwright/test').Page) {
    const { leadId } = loadUatEnv();
    const bookingFromEnv = Number((process.env.UAT_BOOKING_ID || '').trim());

    // Prefer explicit booking id → intake workspace route used by My Bookings Session.
    if (Number.isFinite(bookingFromEnv) && bookingFromEnv > 0) {
      await gotoAppPath(page, `/my-bookings/session/${bookingFromEnv}`);
    } else {
      // Discover a booking for the UAT lead via authenticated API.
      const token = await page.evaluate(
        () => sessionStorage.getItem('token') || localStorage.getItem('token') || ''
      );
      let bookingId: number | null = null;
      if (token) {
        const res = await page.request.get('/api/v1/bookings/mine?limit=50', {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok()) {
          const payload = (await res.json()) as {
            bookings?: Array<{ id?: number; lead_id?: number | null; status?: string }>;
            items?: Array<{ id?: number; lead_id?: number | null; status?: string }>;
          };
          const rows = payload.bookings || payload.items || [];
          const forLead = rows.filter((b) => Number(b.lead_id) === Number(leadId));
          const preferred =
            forLead.find((b) => /SCHEDULED|PENDING/i.test(String(b.status || ''))) || forLead[0];
          bookingId = preferred?.id ? Number(preferred.id) : null;
        }
      }

      if (bookingId) {
        await gotoAppPath(page, `/my-bookings/session/${bookingId}`);
      } else {
        // Last resort: click Session from My Bookings (button or link).
        await gotoAppPath(page, '/my-bookings');
        await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });
        const sessionControl = page
          .getByRole('button', { name: /^Session$/i })
          .or(page.getByRole('link', { name: /^Session$/i }))
          .first();
        if (!(await sessionControl.isVisible().catch(() => false))) {
          test.skip(true, 'No counselling session available for UAT lead');
          return false;
        }
        await sessionControl.click({ force: true });
      }
    }

    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 60_000 });
    await expect(
      workspaceTab(page, /SESSION|PROFILE|DISCOVERY|ROI CALCULATOR/i).first()
    ).toBeVisible({ timeout: 45_000 });
    return true;
  }

  test('Session workspace exposes Session / Profile / Discovery / ROI tabs', async ({
    page,
  }) => {
    const opened = await openUatLeadSession(page);
    if (!opened) return;

    for (const label of [
      /^SESSION$/i,
      /^PROFILE$/i,
      /^DISCOVERY$/i,
      /ROI CALCULATOR/i,
    ]) {
      await expect(workspaceTab(page, label).first()).toBeVisible({
        timeout: 30_000,
      });
    }
  });

  test('Aspirations tab shows editable consultation aspirations surface', async ({ page }) => {
    const opened = await openUatLeadSession(page);
    if (!opened) return;

    await workspaceTab(page, /^PROFILE$/i).click({ force: true });
    await workspaceTab(page, /^Aspirations$/i).click({ force: true });
    await expect(
      page
        .getByText(
          /Aspiration|Destination|Degree|Major|Country|Vision|Preference|Save aspirations|Core Vision/i
        )
        .first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('Session tab renders counselling session notes / status surface', async ({ page }) => {
    const opened = await openUatLeadSession(page);
    if (!opened) return;

    await workspaceTab(page, /^SESSION$/i).click({ force: true });
    await expect(
      page.getByText(/Session|Outcome|Notes|Status|Counsellor|Appointment|Purpose/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('Future Insights tab loads insight surface (or aspirations prerequisite)', async ({
    page,
  }) => {
    const opened = await openUatLeadSession(page);
    if (!opened) return;

    await workspaceTab(page, /^DISCOVERY$/i).click({ force: true });
    await workspaceTab(page, /Future Insights/i).click({ force: true });
    await expect(
      page
        .getByText(
          /Future Insights|Loading Future Insights|target countries|habitat|metro|insight|Add target countries/i
        )
        .first()
    ).toBeVisible({ timeout: 60_000 });
  });

  test('ROI Calculator tab loads calculator surface (or aspirations prerequisite)', async ({
    page,
  }) => {
    const opened = await openUatLeadSession(page);
    if (!opened) return;

    await workspaceTab(page, /ROI Calculator/i).click({ force: true });
    await expect(
      page
        .getByText(
          /ROI Calculator|Loading ROI|NPV|investment|benchmark|Add target countries|ROI %|scenario/i
        )
        .first()
    ).toBeVisible({ timeout: 60_000 });
  });
});
