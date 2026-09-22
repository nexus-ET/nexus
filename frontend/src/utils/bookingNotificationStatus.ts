export type StaffBookingNotificationsLike = {
  whatsapp?: string | null;
  whatsapp_admin?: string | null;
};

export type BookingWhatsAppOutcomeTone = 'success' | 'warning' | 'error' | 'neutral';

export type BookingWhatsAppOutcome = {
  tone: BookingWhatsAppOutcomeTone;
  message: string;
};

export function bookingNotificationLabel(value?: string | null): string {
  const normalized = (value || '').trim().toLowerCase();
  if (!normalized) return 'n/a';
  switch (normalized) {
    case 'sent':
      return 'Sent';
    case 'not_requested':
      return 'Not sent (unchecked)';
    case 'skipped':
      return 'Skipped (missing contact)';
    case 'disabled':
      return 'Disabled in settings';
    case 'failed':
      return 'Failed';
    default:
      return (value || '').trim();
  }
}

function channelFailed(status: string | null | undefined, requested: boolean): boolean {
  return requested && status === 'failed';
}

function channelSent(status: string | null | undefined, requested: boolean): boolean {
  return requested && status === 'sent';
}

export function describeBookingWhatsAppOutcome(
  notifications: StaffBookingNotificationsLike | null | undefined,
  options: {
    candidateRequested: boolean;
    counsellorRequested: boolean;
  }
): BookingWhatsAppOutcome | null {
  const { candidateRequested, counsellorRequested } = options;
  if (!candidateRequested && !counsellorRequested) {
    return {
      tone: 'neutral',
      message: 'WhatsApp notifications were not requested.',
    };
  }

  const candidateStatus = notifications?.whatsapp ?? null;
  const counsellorStatus = notifications?.whatsapp_admin ?? null;

  const candidateSent = channelSent(candidateStatus, candidateRequested);
  const counsellorSent = channelSent(counsellorStatus, counsellorRequested);
  const candidateFailed = channelFailed(candidateStatus, candidateRequested);
  const counsellorFailed = channelFailed(counsellorStatus, counsellorRequested);

  if (candidateFailed && counsellorFailed) {
    return {
      tone: 'error',
      message: 'WhatsApp messages failed for both parties.',
    };
  }

  if (candidateSent && counsellorSent) {
    return {
      tone: 'success',
      message: 'WhatsApp messages sent to both parties.',
    };
  }

  if (candidateSent && counsellorRequested && !counsellorSent && !counsellorFailed) {
    return {
      tone: 'success',
      message: 'WhatsApp message sent to the candidate.',
    };
  }

  if (counsellorSent && candidateRequested && !candidateSent && !candidateFailed) {
    return {
      tone: 'success',
      message: 'WhatsApp message sent to the counsellor.',
    };
  }

  if (candidateSent && counsellorFailed) {
    return {
      tone: 'warning',
      message: 'WhatsApp sent to the candidate, but failed for the counsellor.',
    };
  }

  if (candidateFailed && counsellorSent) {
    return {
      tone: 'warning',
      message: 'WhatsApp sent to the counsellor, but failed for the candidate.',
    };
  }

  if (candidateSent && !counsellorRequested) {
    return {
      tone: 'success',
      message: 'WhatsApp message sent to the candidate.',
    };
  }

  if (counsellorSent && !candidateRequested) {
    return {
      tone: 'success',
      message: 'WhatsApp message sent to the counsellor.',
    };
  }

  if (candidateFailed) {
    return {
      tone: 'error',
      message: 'WhatsApp message failed for the candidate.',
    };
  }

  if (counsellorFailed) {
    return {
      tone: 'error',
      message: 'WhatsApp message failed for the counsellor.',
    };
  }

  return null;
}

export function bookingWhatsAppOutcomeClassName(tone: BookingWhatsAppOutcomeTone): string {
  switch (tone) {
    case 'success':
      return 'text-emerald-900';
    case 'warning':
      return 'text-amber-900';
    case 'error':
      return 'text-rose-900';
    default:
      return 'text-emerald-950/80';
  }
}
