import React from 'react';
import { Outlet } from 'react-router-dom';

const ReportsLayout: React.FC = () => (
  <div className="h-full min-h-0 flex flex-col">
    <Outlet />
  </div>
);

export default ReportsLayout;
