import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { LogOut, UserCircle } from 'lucide-react';

interface UserProfileMenuProps {
  firstName: string;
  lastName: string;
  role: string;
  initials: string;
  onLogout: () => void;
}

const UserProfileMenu: React.FC<UserProfileMenuProps> = ({
  firstName,
  lastName,
  role,
  initials,
  onLogout,
}) => {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

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
        className="flex items-center gap-3 pl-2 rounded-lg hover:bg-surface-bg/80 transition-colors"
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <div className="text-right hidden sm:block">
          <p className="text-xs font-bold text-text-main">
            {firstName}
            {lastName ? ` ${lastName}` : ''}
          </p>
          <p className="text-[10px] font-medium text-text-muted">{role}</p>
        </div>
        <div className="w-9 h-9 rounded-lg bg-surface-bg flex items-center justify-center text-text-main font-bold border border-border-subtle uppercase">
          {initials}
        </div>
      </button>

      {open && (
        <div className="absolute right-0 top-[calc(100%+0.5rem)] min-w-[180px] rounded-xl border border-border-subtle bg-card shadow-xl py-1.5 z-50">
          <Link
            to="/my-profile"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2.5 text-sm text-text-main hover:bg-surface-bg transition-colors"
          >
            <UserCircle size={16} />
            My Profile
          </Link>
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
