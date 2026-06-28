import React from 'react';
import AuditLogViewer from '../components/admin/AuditLogViewer';
import AuditSettings from '../components/admin/Settings';
import SuperAdminRoute from '../components/admin/SuperAdminRoute';

const AuditLogsPage: React.FC = () => (
  <SuperAdminRoute>
    <div className="space-y-6">
      <AuditSettings />
      <AuditLogViewer />
    </div>
  </SuperAdminRoute>
);

export default AuditLogsPage;
