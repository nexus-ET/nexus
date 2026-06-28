import useAuditTracker from '../hooks/useAuditTracker';

/** Captures page visits, button clicks, and field changes for the audit log. */
const AuditTracker: React.FC = () => {
  useAuditTracker();
  return null;
};

export default AuditTracker;
