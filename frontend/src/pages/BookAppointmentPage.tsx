import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import BookAppointmentModal, { type BookAppointmentPrefillLead } from '../components/BookAppointmentModal';

const BookAppointmentPage: React.FC = () => {
  const [searchParams] = useSearchParams();
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

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
      <BookAppointmentModal embedded open initialLead={initialLead} />
    </div>
  );
};

export default BookAppointmentPage;
