import React from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { getStoredToken, hasValidSession } from '../utils/api';
import { queryClient } from '../lib/queryClient';
import { NexusSessionProvider } from '../context/NexusSessionContext';
import { usePresence } from '../hooks/usePresence';
import { useNotifications } from '../hooks/useNotifications';
import NotificationToast from './NotificationToast';

const NexusSessionEffects: React.FC = () => {
  const enabled = hasValidSession() && Boolean(getStoredToken());
  usePresence(enabled);
  useNotifications(enabled);
  return null;
};

const NexusSessionRoot: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <QueryClientProvider client={queryClient}>
    <NexusSessionProvider>
      <NexusSessionEffects />
      {children}
      <NotificationToast />
    </NexusSessionProvider>
  </QueryClientProvider>
);

export default NexusSessionRoot;
