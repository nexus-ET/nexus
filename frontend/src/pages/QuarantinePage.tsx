import React from 'react';
import QuarantineDashboard from '../components/admin/QuarantineDashboard';

const QuarantinePage: React.FC = () => {
  return (
    <div className="h-full overflow-y-auto p-4 md:p-6 lg:p-8">
      <QuarantineDashboard />
    </div>
  );
};

export default QuarantinePage;
