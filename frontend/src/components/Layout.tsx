import React from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Users, 
  ShieldCheck, 
  StickyNote, 
  LogOut,
  Database
} from 'lucide-react';

import NexusLogo from './NexusLogo';
import { clearSession } from '../utils/api';

const Layout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    clearSession();
    navigate('/login');
  };

  const navLinks = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
    { icon: Users, label: 'Student Leads', path: '/clients' },
    { icon: ShieldCheck, label: 'Admin Users', path: '/users' },
    { icon: StickyNote, label: 'Notes', path: '/notes' },
  ];

  return (
    <div className="flex h-screen bg-[#f8fafc] overflow-hidden font-sans">
      {/* Left Sidebar */}
      <aside className="w-64 bg-slate-950 text-slate-300 flex flex-col border-r border-slate-800">
        <div className="h-16 flex items-center px-6 border-b border-slate-800/50">
          <div className="flex items-center gap-3">
            <NexusLogo size={32} />
            <span className="font-inter text-lg font-extrabold tracking-tight text-white">
              Nexus Intel
            </span>
          </div>
        </div>

        <nav className="flex-1 py-6 px-3 space-y-1">
          {navLinks.map((link) => (
            <Link
              key={link.path}
              to={link.path}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${
                location.pathname === link.path 
                ? 'bg-indigo-600 text-white shadow-md' 
                : 'hover:bg-slate-900 hover:text-slate-100'
              }`}
            >
              <link.icon size={18} />
              <span className="text-sm font-medium">{link.label}</span>
            </Link>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-800/50">
          <button onClick={handleLogout} className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg hover:bg-red-900/20 hover:text-red-400 transition-all text-sm font-medium text-slate-500">
            <LogOut size={18} /> Logout
          </button>
        </div>
      </aside>

      {/* Workspace Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <main className="flex-1 overflow-y-auto relative">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default Layout;