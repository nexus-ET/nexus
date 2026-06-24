import React from 'react';
import { Outlet, Link, useNavigate } from 'react-router-dom';

const Layout: React.FC = () => {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Left Navigation */}
      <aside className="w-64 bg-slate-800 text-white flex flex-col">
        <div className="p-6 text-2xl font-bold border-b border-slate-700">
          NEXUS
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <Link to="/dashboard" className="block p-3 rounded hover:bg-slate-700 transition-colors">
            📊 Dashboard
          </Link>
          <Link to="/clients" className="block p-3 rounded hover:bg-slate-700 transition-colors">
            👥 Clients
          </Link>
          <Link to="/users" className="block p-3 rounded hover:bg-slate-700 transition-colors">
            🛡️ Users
          </Link>
          <Link to="/notes" className="block p-3 rounded hover:bg-slate-700 transition-colors">
            📝 Notes
          </Link>
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Navigation */}
        <header className="h-16 bg-white shadow-sm flex items-center justify-between px-8">
          <h2 className="text-xl font-semibold text-gray-800">System Overview</h2>
          <div className="flex items-center space-x-4">
            <span className="text-sm text-gray-600">Admin User</span>
            <button 
              onClick={handleLogout}
              className="bg-red-50 text-red-600 px-4 py-2 rounded-md hover:bg-red-100 transition-colors"
            >
              Logout
            </button>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-x-hidden overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default Layout;