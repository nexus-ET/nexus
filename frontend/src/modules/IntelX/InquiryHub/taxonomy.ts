import type { InquiryNode } from './types';

/** Local shape keeps hierarchy selectors available while the API is loading. */
export const INQUIRY_HIERARCHY: InquiryNode[] = [
  { code: '1', name: 'Counselling', children: [
    { code: '1.1', name: 'Intake Session', children: [] },
    { code: '1.2', name: 'Candidate Registration', children: [] },
    { code: '1.3', name: 'Profile Creation', children: [] },
  ] },
  { code: '2', name: 'College Finding', children: [
    { code: '2.1', name: 'Shortlist Target Colleges', children: [] },
    { code: '2.2', name: 'Confirm Program Fit', children: [] },
    { code: '2.3', name: 'University Outreach', children: [] },
    { code: '2.4', name: 'Finalize Target Colleges', children: [] },
  ] },
  { code: '3', name: 'Document Readiness', children: [
    { code: '3.1', name: 'Academic Transcripts', children: [] },
    { code: '3.2', name: 'Standardized Test Scores', children: [
      { code: '3.2.1', name: 'Confirm Required Tests', children: [] },
      { code: '3.2.2', name: 'Book Exam Slot', children: [] },
      { code: '3.2.3', name: 'Upload Score Report', children: [] },
    ] },
    { code: '3.3', name: 'Financial Proofs', children: [] },
    { code: '3.4', name: 'Statement of Purpose (SOP)', children: [] },
    { code: '3.5', name: 'Recommendation Letters (LORs)', children: [] },
    { code: '3.6', name: 'Identity & Passport', children: [] },
  ] },
  { code: '4', name: 'Admission Processing', children: [
    { code: '4.1', name: 'Application Submission', children: [] },
    { code: '4.2', name: 'Tuition & Fee Payment', children: [] },
    { code: '4.3', name: 'Final Offer & Visa Documentation', children: [] },
  ] },
  { code: '5', name: 'Visa Processing', children: [
    { code: '5.1', name: 'Document & Financials', children: [] },
    { code: '5.2', name: 'Visa Application', children: [] },
    { code: '5.3', name: 'Biometrics & Medical Examination', children: [] },
    { code: '5.4', name: 'Visa Interview Preparation', children: [] },
    { code: '5.5', name: 'Visa Decision & Issuance', children: [] },
  ] },
  { code: '6', name: 'Pre-Departure & Travel', children: [
    { code: '6.1', name: 'Travel Booking', children: [] },
    { code: '6.2', name: 'Accommodation', children: [] },
    { code: '6.3', name: 'Orientation', children: [] },
    { code: '6.4', name: 'Compliance & FX', children: [] },
    { code: '6.5', name: 'Arrival Tracking', children: [] },
  ] },
  { code: '7', name: 'Landing', children: [
    { code: '7.1', name: 'Airport Arrival', children: [] },
    { code: '7.2', name: 'Campus Check-In', children: [] },
    { code: '7.3', name: 'Settling In', children: [] },
    { code: '7.4', name: 'Bank & Telecom', children: [] },
    { code: '7.5', name: 'Academic Registration', children: [] },
  ] },
  { code: 'OTHER', name: 'Others', children: [] },
];

export function findInquiryNode(nodes: InquiryNode[], code: string): InquiryNode | undefined {
  for (const node of nodes) {
    if (node.code === code) return node;
    const nested = findInquiryNode(node.children, code);
    if (nested) return nested;
  }
  return undefined;
}
