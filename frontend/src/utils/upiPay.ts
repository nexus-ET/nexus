import { roundMoney } from './invoiceMoney';

/** Build a UPI intent string for GPay / PhonePe / Paytm. */
export function buildUpiPayUri(input: {
  vpa: string;
  payeeName: string;
  amountInr: number;
  note?: string;
  transactionRef?: string;
}): string | null {
  const pa = input.vpa.trim();
  if (!pa || !pa.includes('@')) return null;
  const params = new URLSearchParams();
  params.set('pa', pa);
  params.set('pn', input.payeeName.trim() || 'Nexus');
  params.set('cu', 'INR');
  const amount = roundMoney(Math.max(0, input.amountInr));
  if (amount > 0) params.set('am', amount.toFixed(2));
  if (input.note?.trim()) params.set('tn', input.note.trim().slice(0, 80));
  if (input.transactionRef?.trim()) params.set('tr', input.transactionRef.trim().slice(0, 35));
  return `upi://pay?${params.toString()}`;
}

/** External QR image URL (no extra npm dependency). */
export function upiQrImageUrl(upiUri: string, size = 180): string {
  return `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&data=${encodeURIComponent(upiUri)}`;
}
