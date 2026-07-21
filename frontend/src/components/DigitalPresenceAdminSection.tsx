import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { apiFetch } from '../utils/api';
import DigitalPresenceLinksList from './DigitalPresenceLinksList';
import type { DigitalPresenceLinkRecord, DigitalPresenceLinksResponse } from '../types/digitalPresenceLink';

interface DigitalPresenceAdminSectionProps {
  leadId: number;
}

const DigitalPresenceAdminSection: React.FC<DigitalPresenceAdminSectionProps> = ({ leadId }) => {
  const [links, setLinks] = useState<DigitalPresenceLinkRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    apiFetch(`leads/${leadId}/digital-presence-links`)
      .then(response => {
        if (cancelled) return;
        setLinks((response as DigitalPresenceLinksResponse).links);
      })
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load digital presence links.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [leadId]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-text-muted py-2">
        <Loader2 size={16} className="animate-spin" />
        Loading digital presence…
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  return (
    <div className="prospects-profile-grid__wide space-y-2">
      <span>Digital Presence</span>
      <DigitalPresenceLinksList links={links} readOnly showCategoryFilter />
    </div>
  );
};

export default DigitalPresenceAdminSection;
