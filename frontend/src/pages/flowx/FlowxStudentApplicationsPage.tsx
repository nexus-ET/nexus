import StudentApplicationsPanel from '../../components/flowx/StudentApplicationsPanel';
import { useParams } from 'react-router-dom';

/**
 * Student applications hub — all country/college journeys for one lead.
 * Global /flowx/journeys list was moved into the counselling session workspace.
 */
const FlowxStudentApplicationsPage: React.FC = () => {
  const { leadId: leadIdParam } = useParams<{ leadId: string }>();
  const leadId = Number(leadIdParam);

  if (!Number.isFinite(leadId) || leadId <= 0) {
    return <p className="text-sm text-red-700">Invalid student lead id.</p>;
  }

  return (
    <StudentApplicationsPanel leadId={leadId} showTestControls embedded={false} />
  );
};

export default FlowxStudentApplicationsPage;
