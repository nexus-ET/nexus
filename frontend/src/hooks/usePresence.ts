import { useEffect, useRef } from 'react';
import { apiFetch, getStoredToken, hasValidSession } from '../utils/api';
import { connectNexusWebSocket, NexusSocketHandle } from '../utils/nexusWebSocket';

const HEARTBEAT_MS = 60_000;

/** Keeps the admin online via WebSocket ping + REST heartbeat on every authenticated route. */
export function usePresence(enabled: boolean): void {
  const socketRef = useRef<NexusSocketHandle | null>(null);
  const heartbeatRef = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled || !hasValidSession()) return;

    const sendHeartbeat = () => {
      if (!getStoredToken()) return;
      void apiFetch('chat/messaging/heartbeat', {
        method: 'POST',
        body: JSON.stringify({}),
        authRedirect: false,
      }).catch(
        () => {
          // Messaging hub may be disabled for this role.
        }
      );
      socketRef.current?.send({ type: 'ping' });
    };

    socketRef.current = connectNexusWebSocket({
      onOpen: () => {
        sendHeartbeat();
      },
    });

    heartbeatRef.current = window.setInterval(sendHeartbeat, HEARTBEAT_MS);

    return () => {
      if (heartbeatRef.current != null) {
        window.clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [enabled]);
}
