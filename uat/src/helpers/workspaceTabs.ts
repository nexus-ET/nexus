import { type Page } from '@playwright/test';

/**
 * Intake session / credentials workspace nav renders `<button role="tab">`.
 * Use role tab (not button) so Playwright matches the accessible name.
 */
export function workspaceTab(page: Page, name: string | RegExp) {
  return page.getByRole('tab', { name });
}

/** Top-level intake workspace tabs (SESSION, PROFILE, DISCOVERY, ROI CALCULATOR). */
export function expectIntakeWorkspaceTabs(page: Page) {
  return workspaceTab(page, /SESSION|PROFILE|DISCOVERY|ROI CALCULATOR/i).first();
}
