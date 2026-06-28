import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import {
  flushAuditEvents,
  getClickTarget,
  isChoiceField,
  isTextLikeField,
  trackFieldChange,
  trackPageView,
  trackUiClick,
} from '../utils/auditTracker';
import { hasValidSession } from '../utils/api';

const useAuditTracker = (): void => {
  const location = useLocation();

  useEffect(() => {
    if (!hasValidSession()) return;
    trackPageView(location.pathname);
  }, [location.pathname]);

  useEffect(() => {
    if (!hasValidSession()) return;

    const onClick = (event: MouseEvent) => {
      const target = getClickTarget(event.target);
      if (!target) return;
      trackUiClick(target);
    };

    const onChange = (event: Event) => {
      if (!isChoiceField(event.target)) return;
      trackFieldChange(event.target);
    };

    const inputTimers = new Map<string, number>();
    const onInput = (event: Event) => {
      if (!isTextLikeField(event.target)) return;
      const key = event.target.id || event.target.name || event.target.tagName;
      const now = Date.now();
      const last = inputTimers.get(key) || 0;
      if (now - last < 2000) return;
      inputTimers.set(key, now);
      trackFieldChange(event.target);
    };

    document.addEventListener('click', onClick, true);
    document.addEventListener('change', onChange, true);
    document.addEventListener('input', onInput, true);

    return () => {
      document.removeEventListener('click', onClick, true);
      document.removeEventListener('change', onChange, true);
      document.removeEventListener('input', onInput, true);
      void flushAuditEvents();
    };
  }, []);
};

export default useAuditTracker;
