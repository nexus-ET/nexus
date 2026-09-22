import React, { useMemo } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import BookAppointmentModal, { type BookAppointmentPrefillLead } from '../components/BookAppointmentModal';
import { bookAppointmentReturnTo } from '../utils/bookAppointmentHref';

const BookAppointmentPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = useMemo(
    () => bookAppointmentReturnTo(searchParams.get('returnTo')),
    [searchParams]
  );
  const initialLead = useMemo<BookAppointmentPrefillLead | null>(() => {
    const leadId = Number(searchParams.get('leadId'));
    if (!Number.isFinite(leadId) || leadId <= 0) return null;
    return {
      id: leadId,
      full_name: searchParams.get('name'),
      email: searchParams.get('email'),
      phone_number: searchParams.get('phone'),
    };
  }, [searchParams]);

  const backLabel = returnTo.startsWith('/offline-leads')
    ? 'Back to All Leads'
    : 'Back';

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
      <div className="mb-4">
        <button
          type="button"
          onClick={() => navigate(returnTo)}
          className="inline-flex items-center gap-2 rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm font-semibold text-text-main hover:bg-surface-bg"
        >
          <ArrowLeft size={16} />
          {backLabel}
        </button>
      </div>
      <BookAppointmentModal
        embedded
        open
        initialLead={initialLead}
        returnTo={returnTo}
      />
    </div>
  );
};

export default BookAppointmentPage;
