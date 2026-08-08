import React from 'react';
import BookAppointmentModal from '../components/BookAppointmentModal';

const BookAppointmentPage: React.FC = () => {
  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
      <BookAppointmentModal embedded open />
    </div>
  );
};

export default BookAppointmentPage;
