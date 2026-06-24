import React from 'react';
import SyncLogs from '../components/reports/SyncLogs';

const ReportsPage: React.FC = () => {
  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 lg:p-8">
      <SyncLogs />
    </div>
  );
};

export default ReportsPage;
