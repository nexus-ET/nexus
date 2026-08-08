import { useMemo } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import CounsellingSessionDrawer from '../components/CounsellingSessionDrawer';

/**
 * Route wrapper: keeps My Appointments underneath and opens the session as a
 * right-hand slide-over so the user does not lose list context.
 */
const MyBookingSessionPage: React.FC = () => {
  const { bookingId: bookingIdParam } = useParams<{ bookingId?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const bookingId = useMemo(() => {
    if (!bookingIdParam) return null;
    const n = Number(bookingIdParam);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [bookingIdParam]);

  const candidateId = useMemo(() => {
    const raw =
      searchParams.get('candidateId') ||
      searchParams.get('leadId') ||
      searchParams.get('candidate_id');
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [searchParams]);

  const candidateName = searchParams.get('name')?.trim() || null;
  const dateLabel = searchParams.get('date')?.trim() || null;
  const timeLabel = searchParams.get('time')?.trim() || null;

  if (!bookingId && !candidateId) {
    return <Navigate to="/my-bookings" replace />;
  }

  return (
    <CounsellingSessionDrawer
      open
      bookingId={bookingId}
      candidateId={candidateId}
      candidateName={candidateName}
      dateLabel={dateLabel}
      timeLabel={timeLabel}
      onClose={() => navigate('/my-bookings')}
    />
  );
};

export default MyBookingSessionPage;
