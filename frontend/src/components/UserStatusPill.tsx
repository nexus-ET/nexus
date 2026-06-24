import React from 'react';

interface UserStatusPillProps {
  isActive?: boolean;
  statusReason?: string | null;
}

export const UserStatusPill: React.FC<UserStatusPillProps> = ({
  isActive = true,
  statusReason,
}) => {
  if (isActive) {
    return (
      <span className="text-green-600 bg-green-100 px-2.5 py-1 rounded-full text-[10px] font-black uppercase">
        Active
      </span>
    );
  }

  return (
    <span
      className="text-red-600 bg-red-100 px-2.5 py-1 rounded-full text-[10px] font-black uppercase"
      title={statusReason || 'Inactive'}
    >
      {statusReason || 'Inactive'}
    </span>
  );
};

export default UserStatusPill;
