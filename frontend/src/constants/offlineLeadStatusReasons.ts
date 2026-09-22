/** Reason lists for All Leads active ↔ inactive transitions (max 5 each). */
export const OFFLINE_LEAD_INACTIVE_REASONS = [
  'Course Completed',
  'Fee Due / Non-Payment',
  'Dropped Out',
  'Personal Reasons',
  'Unresponsive',
] as const;

export const OFFLINE_LEAD_ACTIVE_REASONS = [
  'Fee Cleared / Paid',
  'Re-enrollment Requested',
  'Deferral Ended',
  'Administrative Correction',
  'Other',
] as const;

export type OfflineLeadInactiveReason = (typeof OFFLINE_LEAD_INACTIVE_REASONS)[number];
export type OfflineLeadActiveReason = (typeof OFFLINE_LEAD_ACTIVE_REASONS)[number];
