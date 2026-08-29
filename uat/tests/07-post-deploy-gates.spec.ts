import { expect, test } from '@playwright/test';
import { requireCredentials } from '../src/helpers/env';

/**
 * Hard gates for issues that burned staging BAU on 2026-08-08.
 * These hit APIs (not just page loads) so WhatsApp/template/sequence
 * regressions fail CI/UAT before handoff.
 */
test.describe('Post-deploy regression gates', () => {
  test('API login + status definitions are healthy', async ({ request }) => {
    const { baseUrl, email, password } = requireCredentials();
    const login = await request.post(`${baseUrl}/api/v1/login`, {
      form: { username: email, password },
    });
    expect(login.ok(), await login.text()).toBeTruthy();
    const token = (await login.json()).access_token as string;
    expect(token).toBeTruthy();

    const defs = await request.get(`${baseUrl}/api/v1/leads/status-definitions`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(defs.ok(), await defs.text()).toBeTruthy();
  });

  test('TOEFL score capture does not 500 (sequence + schema gate)', async ({ request }) => {
    const { baseUrl, email, password, leadId } = requireCredentials();
    const login = await request.post(`${baseUrl}/api/v1/login`, {
      form: { username: email, password },
    });
    expect(login.ok(), await login.text()).toBeTruthy();
    const token = (await login.json()).access_token as string;
    const headers = { Authorization: `Bearer ${token}` };

    const bookingFromEnv = Number((process.env.UAT_BOOKING_ID || '').trim());
    let bookingId: number | null =
      Number.isFinite(bookingFromEnv) && bookingFromEnv > 0 ? bookingFromEnv : null;

    const mine = await request.get(`${baseUrl}/api/v1/bookings/mine`, { headers });
    expect(mine.ok(), await mine.text()).toBeTruthy();
    const payload = await mine.json();
    if (!bookingId) {
      for (const section of ['today', 'upcoming', 'past'] as const) {
        for (const row of payload[section] || []) {
          if (row?.id) {
            bookingId = Number(row.id);
            break;
          }
        }
        if (bookingId) break;
      }
    }

    // Create a disposable far-future booking only when no fixture exists (avoid slow Meta notifications).
    if (!bookingId) {
      const day = new Date();
      day.setUTCDate(day.getUTCDate() + 21);
      const dateKey = day.toISOString().slice(0, 10);
      const avail = await request.get(`${baseUrl}/api/v1/bookings/availability`, {
        headers,
        params: { admin_id: 1, date: dateKey },
      });
      if (avail.ok()) {
        const slot = ((await avail.json()).slots || []).find(
          (item: { available?: boolean }) => item.available
        );
        if (slot?.start) {
          const create = await request.post(`${baseUrl}/api/v1/bookings/staff`, {
            headers,
            timeout: 120_000,
            data: {
              scheduled_time: slot.start,
              admin_id: 1,
              candidate_name: 'UAT Gate Student',
              candidate_email: email,
              lead_id: Number(leadId) || null,
              session_purpose: 'General Counselling',
              notes: 'Purpose: General Counselling',
            },
          });
          expect(create.ok(), await create.text()).toBeTruthy();
          const body = await create.json();
          bookingId = Number(body.id);
          const notifications = body.notifications || {};
          for (const channel of ['email', 'email_admin'] as const) {
            const status = notifications[channel];
            expect(
              ['sent', 'skipped', 'disabled', undefined].includes(status),
              `${channel}=${status}`
            ).toBeTruthy();
          }
          for (const channel of ['whatsapp', 'whatsapp_admin'] as const) {
            const status = notifications[channel];
            expect(
              status !== 'failed',
              `${channel} failed — Meta booking template/WABA/language gate`
            ).toBeTruthy();
          }
        }
      }
    }

    expect(bookingId, 'Need a booking id for TOEFL save gate').toBeTruthy();

    const save = await request.post(`${baseUrl}/api/v1/bookings/mine/${bookingId}/test-scores`, {
      headers,
      data: {
        test_name: 'TOEFL',
        overall_score: '110',
        sections: [
          { section_name: 'Reading', score: '28' },
          { section_name: 'Listening', score: '28' },
          { section_name: 'Speaking', score: '27' },
          { section_name: 'Writing', score: '27' },
        ],
      },
    });
    expect(
      save.status(),
      `TOEFL save HTTP ${save.status()}: ${(await save.text()).slice(0, 300)}`
    ).toBe(200);
    const scores = (await save.json()).scores || [];
    expect(scores.length).toBeGreaterThan(0);
  });

  test('Book Appointment and Exception Report routes render', async ({ page }) => {
    await page.goto('/book-appointment');
    await expect(page.getByRole('heading', { name: /book appointment/i }).first()).toBeVisible({
      timeout: 60_000,
    });
    await page.goto('/reports/exceptions');
    await expect(page.locator('body')).toContainText(/exception/i, { timeout: 60_000 });
  });
});
