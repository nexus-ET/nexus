import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Brain, LogOut, UserCircle } from 'lucide-react';
import { useIntelPreferences, useUpdateIntelPreferences } from '../hooks/useNexusIntel';

interface UserProfileMenuProps {
  firstName: string;
  lastName: string;
  role: string;
  initials: string;
  onLogout: () => void;
  onDarkHeader?: boolean;
}

const UserProfileMenu: React.FC<UserProfileMenuProps> = ({
  firstName,
  lastName,
  role,
  initials,
  onLogout,
  onDarkHeader = false,
}) => {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const prefsQuery = useIntelPreferences();
  const updatePrefs = useUpdateIntelPreferences();
  const prefs = prefsQuery.data;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    window.addEventListener('mousedown', handleClickOutside);
    return () => window.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        className={`flex items-center gap-3 pl-2 rounded-lg transition-colors ${
          onDarkHeader ? 'hover:bg-white/10' : 'hover:bg-surface-bg/80'
        }`}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <div className="text-right hidden sm:block">
          <p className={`text-xs font-bold ${onDarkHeader ? 'text-white' : 'text-text-main'}`}>
            {firstName}
            {lastName ? ` ${lastName}` : ''}
          </p>
          <p className={`text-[10px] font-medium ${onDarkHeader ? 'text-white/70' : 'text-text-muted'}`}>
            {role}
          </p>
        </div>
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center font-bold border uppercase ${
            onDarkHeader
              ? 'bg-white/15 text-white border-white/25'
              : 'bg-surface-bg text-text-main border-border-subtle'
          }`}
        >
          {initials}
        </div>
      </button>

      {open && (
        <div className="absolute right-0 top-[calc(100%+0.5rem)] min-w-[220px] rounded-xl border border-border-subtle bg-card shadow-xl py-1.5 z-50">
          <Link
            to="/my-profile"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2.5 text-sm text-text-main hover:bg-surface-bg transition-colors"
          >
            <UserCircle size={16} />
            My Profile
          </Link>
          <Link
            to="/nexus-intel/controls"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2.5 text-sm text-text-main hover:bg-surface-bg transition-colors"
          >
            <Brain size={16} />
            Nexus Intel controls
          </Link>
          <div className="my-1 border-t border-border-subtle" />
          <label className="flex items-center justify-between gap-3 px-3 py-2 text-xs text-text-main hover:bg-surface-bg cursor-pointer">
            <span>Show Intel Tips</span>
            <input
              type="checkbox"
              checked={prefs?.enable_contextual_tips ?? true}
              onChange={e => updatePrefs.mutate({ enable_contextual_tips: e.target.checked })}
              className="h-3.5 w-3.5"
            />
          </label>
          <label className="flex items-center justify-between gap-3 px-3 py-2 text-xs text-text-main hover:bg-surface-bg cursor-pointer">
            <span>Daily Trivia</span>
            <input
              type="checkbox"
              checked={prefs?.enable_daily_trivia ?? true}
              onChange={e => updatePrefs.mutate({ enable_daily_trivia: e.target.checked })}
              className="h-3.5 w-3.5"
            />
          </label>
          <div className="my-1 border-t border-border-subtle" />
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-red-700 hover:bg-red-50 transition-colors"
          >
            <LogOut size={16} />
            Logout
          </button>
        </div>
      )}
    </div>
  );
};

export default UserProfileMenu;
