import React, { useRef } from 'react';
import ExceptionLogs from '../components/reports/ExceptionLogs';
import ExceptionRetentionSettings from '../components/reports/ExceptionRetentionSettings';

const ExceptionReportPage: React.FC = () => {
  const refreshRef = useRef<(() => void) | null>(null);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 lg:p-8 space-y-6">
      <ExceptionRetentionSettings onPurged={() => refreshRef.current?.()} />
      <ExceptionLogs refreshRef={refreshRef} />
    </div>
  );
};

export default ExceptionReportPage;
