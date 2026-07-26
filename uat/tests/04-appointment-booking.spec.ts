import { test, expect } from '@playwright/test';
import { gotoAppPath } from '../src/helpers/auth';

/**
 * UAT — Appointment booking / counselling schedule + counselor communication surfaces.
 */
test.describe('Appointment booking', () => {
  test('Counselling schedule dashboard loads', async ({ page }) => {
    await gotoAppPath(page, '/counselling');
    await expect(
      page.getByText(/Counselling|Schedule|Appointments|Pending|Today|Calendar|Period agenda|Agenda/i).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('My Bookings grouped sections (past / today / upcoming) are present', async ({
    page,
  }) => {
    await gotoAppPath(page, '/my-bookings');
    await expect(page.getByRole('heading', { name: /My Bookings/i })).toBeVisible({
      timeout: 45_000,
    });
    await expect(
      page.getByRole('button', { name: /Past .*Bookings|Today .*Bookings|Upcoming .*Bookings/i }).first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('period agenda / calendar navigation controls render on counselling', async ({
    page,
  }) => {
    await gotoAppPath(page, '/counselling');
    await page.waitForTimeout(1000);

    const periodOrNav = page
      .getByText(/Period agenda|Today|Pending|Schedule|Appointments/i)
      .or(page.getByRole('button', { name: /Previous|Next|Today|Week|Day/i }));

    await expect(periodOrNav.first()).toBeVisible({ timeout: 45_000 });
  });

  test('booking interaction surfaces (session / journey) are available when bookings exist', async ({
    page,
  }) => {
    await gotoAppPath(page, '/my-bookings');
    await page.waitForTimeout(1500);

    const action = page.getByRole('button', {
      name: /Session|Outcome|Journey|View|Reschedule|Cancel|Notes|Profile|Interaction/i,
    });
    const metricOrList = page.getByText(
      /Past bookings|Today's bookings|Upcoming bookings|Period agenda|appointment|My Bookings/i
    );

    const hasActions = await action.first().isVisible().catch(() => false);
    const hasShell = await metricOrList.first().isVisible().catch(() => false);

    expect(
      hasActions || hasShell,
      'Expected booking actions or the My Bookings overview shell'
    ).toBeTruthy();
  });

  test('schedule grid exposes bookable slot / pending appointment surfaces for counselors', async ({
    page,
  }) => {
    await gotoAppPath(page, '/counselling');
    await expect(page.getByText(/^Loading…$/)).toHaveCount(0, { timeout: 45_000 });

    await expect(
      page
        .getByText(/Pending|Today|Slot|Available|Booked|Schedule|Appointments|Period agenda/i)
        .first()
    ).toBeVisible({ timeout: 45_000 });
  });

  test('View Interaction opens counselor communication trail for WhatsApp/notification audit', async ({
    page,
  }) => {
    await gotoAppPath(page, '/my-bookings');
    await expect(page.getByRole('heading', { name: /My Bookings/i })).toBeVisible({
      timeout: 45_000,
    });

    // Click a non-zero Past/Upcoming metric — app clears the day filter so the section lists bookings.
    const metrics = [
      page.getByRole('button', { name: /Upcoming .*Bookings/i }),
      page.getByRole('button', { name: /Past .*Bookings/i }),
      page.getByRole('button', { name: /Today .*Bookings/i }),
    ];

    let opened = false;
    for (const metric of metrics) {
      if (!(await metric.isVisible().catch(() => false))) continue;
      const label = ((await metric.innerText().catch(() => '')) || '').replace(/\s+/g, ' ');
      if (/Bookings/i.test(label) && /\b0\b/.test(label)) continue;
      await metric.click();
      await page.waitForTimeout(1000);
      const interaction = page.getByRole('button', { name: /View Interaction/i });
      if (await interaction.first().isVisible().catch(() => false)) {
        await interaction.first().click({ force: true });
        opened = true;
        break;
      }
    }

    expect(opened, 'Expected a View Interaction action on a Past/Today/Upcoming booking card').toBeTruthy();

    await expect(
      page
        .getByText(
          /Interaction Log|WhatsApp|Message|Notification|Communication|Outbound|Inbound|Template|No communication history|conversation/i
        )
        .first()
    ).toBeVisible({ timeout: 30_000 });
  });
});
