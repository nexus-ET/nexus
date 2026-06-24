import { useCallback, useEffect, useState } from 'react';
import { apiFetch, hasValidSession } from '../utils/api';
import { firebaseConfig, firebaseVapidKey, isFirebaseConfigured } from '../config/firebase';

export type PushSupportState = 'unsupported' | 'blocked' | 'ready' | 'registered' | 'error';

const isIOSDevice = () =>
  /iPad|iPhone|iPod/.test(navigator.userAgent) ||
  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

const prefersInAppAlerts = () => {
  if (isIOSDevice()) return true;
  if (!('serviceWorker' in navigator)) return true;
  if (!('PushManager' in window)) return true;
  if (!('Notification' in window)) return true;
  return false;
};

export const usePushNotifications = () => {
  const [supportState, setSupportState] = useState<PushSupportState>('unsupported');
  const [error, setError] = useState<string | null>(null);
  const [useInAppFallback, setUseInAppFallback] = useState(false);

  const registerPushToken = useCallback(async () => {
    if (!hasValidSession()) return;
    if (prefersInAppAlerts()) {
      setUseInAppFallback(true);
      setSupportState('unsupported');
      setError(null);
      return;
    }
    if (!isFirebaseConfigured()) {
      setUseInAppFallback(true);
      setSupportState('unsupported');
      return;
    }

    try {
      const [{ initializeApp, getApps }, { getMessaging, isSupported, getToken, onMessage }] =
        await Promise.all([import('firebase/app'), import('firebase/messaging')]);

      const supported = await isSupported();
      if (!supported) {
        setUseInAppFallback(true);
        setSupportState('unsupported');
        return;
      }

      setSupportState('ready');

      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setUseInAppFallback(true);
        setSupportState('blocked');
        return;
      }

      const firebaseApp = getApps().length ? getApps()[0]! : initializeApp(firebaseConfig);
      const messaging = getMessaging(firebaseApp);

      await navigator.serviceWorker.register('/firebase-messaging-sw.js');
      const registration = await navigator.serviceWorker.ready;

      const token = await getToken(messaging, {
        vapidKey: firebaseVapidKey,
        serviceWorkerRegistration: registration,
      });

      if (!token) {
        setUseInAppFallback(true);
        setSupportState('error');
        setError('Unable to obtain push token.');
        return;
      }

      await apiFetch('notifications/push-token', {
        method: 'POST',
        body: JSON.stringify({ token }),
      });

      onMessage(messaging, () => {
        window.dispatchEvent(new CustomEvent('nexus:notifications-refresh'));
      });

      setUseInAppFallback(false);
      setSupportState('registered');
      setError(null);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Push registration failed.';
      if (message.includes('firebase') || message.includes('Failed to resolve')) {
        setUseInAppFallback(true);
        setSupportState('unsupported');
        setError('Install the firebase package: npm install (in the frontend folder).');
        return;
      }
      setUseInAppFallback(true);
      setSupportState('error');
      setError(message);
    }
  }, []);

  useEffect(() => {
    if (!hasValidSession()) {
      setSupportState('unsupported');
      return;
    }
    registerPushToken();
  }, [registerPushToken]);

  return {
    supportState,
    error,
    registerPushToken,
    useInAppFallback,
    isPushSupported: supportState !== 'unsupported' && supportState !== 'blocked',
  };
};
