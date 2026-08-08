/** Constants and helpers for FlowX Add Application form. */

export const FLOWX_PATHWAY_TYPES = [
  { value: 'centralized_national_portal', label: 'Centralized national portal' },
  { value: 'regional_clearing_agency', label: 'Regional clearing agency' },
  { value: 'direct_institutional_portal', label: 'Direct institutional portal' },
  { value: 'third_party_aggregator', label: 'Third-party aggregator' },
  { value: 'partner_portal', label: 'Partner portal' },
  { value: 'paper_offline_route', label: 'Paper / offline route' },
] as const;

export const FLOWX_APPLICATION_STATUSES = [
  { value: 'drafting', label: 'Drafting' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'under_review', label: 'Under review' },
  { value: 'conditional_offer', label: 'Conditional offer' },
  { value: 'unconditional_offer', label: 'Unconditional offer' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'deferred', label: 'Deferred' },
] as const;

export const FLOWX_FEE_STATUSES = [
  { value: 'not_required', label: 'Not required' },
  { value: 'pending_payment', label: 'Pending payment' },
  { value: 'paid', label: 'Paid' },
  { value: 'fee_waiver', label: 'Fee waiver' },
] as const;

export const FLOWX_FEE_CURRENCIES = ['USD', 'GBP', 'EUR', 'CAD', 'AUD', 'NZD', 'SGD', 'JPY', 'INR'] as const;

export const CUSTOM_PATHWAY_SENTINEL = '__custom__';
