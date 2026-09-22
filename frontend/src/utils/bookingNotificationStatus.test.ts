import { describe, expect, it } from 'vitest';
import {
  bookingNotificationLabel,
  describeBookingWhatsAppOutcome,
} from './bookingNotificationStatus';

describe('bookingNotificationLabel', () => {
  it('maps known backend statuses to user-facing labels', () => {
    expect(bookingNotificationLabel('sent')).toBe('Sent');
    expect(bookingNotificationLabel('failed')).toBe('Failed');
    expect(bookingNotificationLabel('not_requested')).toBe('Not sent (unchecked)');
    expect(bookingNotificationLabel('skipped')).toBe('Skipped (missing contact)');
    expect(bookingNotificationLabel('disabled')).toBe('Disabled in settings');
  });
});

describe('describeBookingWhatsAppOutcome', () => {
  it('reports success when both requested channels were sent', () => {
    expect(
      describeBookingWhatsAppOutcome(
        { whatsapp: 'sent', whatsapp_admin: 'sent' },
        { candidateRequested: true, counsellorRequested: true }
      )
    ).toEqual({
      tone: 'success',
      message: 'WhatsApp messages sent to both parties.',
    });
  });

  it('only reports both-party failure when both requested channels failed', () => {
    expect(
      describeBookingWhatsAppOutcome(
        { whatsapp: 'failed', whatsapp_admin: 'failed' },
        { candidateRequested: true, counsellorRequested: true }
      )
    ).toEqual({
      tone: 'error',
      message: 'WhatsApp messages failed for both parties.',
    });
  });

  it('does not treat skipped or not_requested as failure when requested', () => {
    expect(
      describeBookingWhatsAppOutcome(
        { whatsapp: 'sent', whatsapp_admin: 'not_requested' },
        { candidateRequested: true, counsellorRequested: true }
      )
    ).toEqual({
      tone: 'success',
      message: 'WhatsApp message sent to the candidate.',
    });

    expect(
      describeBookingWhatsAppOutcome(
        { whatsapp: 'skipped', whatsapp_admin: 'skipped' },
        { candidateRequested: true, counsellorRequested: true }
      )
    ).toBeNull();
  });
});
