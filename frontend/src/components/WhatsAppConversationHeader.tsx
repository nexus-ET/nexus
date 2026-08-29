import React from 'react';
import { MessageCircle, MoreVertical, Phone } from 'lucide-react';

interface WhatsAppConversationHeaderProps {
  name: string;
  meta: string;
  mode: 'ai' | 'handoff';
  actions?: React.ReactNode;
}

const initialsFor = (name: string): string =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0]?.toUpperCase())
    .join('') || 'WA';

const WhatsAppConversationHeader: React.FC<WhatsAppConversationHeaderProps> = ({
  name,
  meta,
  mode,
  actions,
}) => (
  <header
    style={{
      minHeight: '76px',
      padding: '10px 18px',
      background: 'linear-gradient(135deg, #155e52 0%, #124d46 100%)',
      color: '#ffffff',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '14px',
      flexShrink: 0,
      boxShadow: '0 2px 8px rgba(15, 76, 69, 0.2)',
      boxSizing: 'border-box',
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0, flex: 1 }}>
      <div
        aria-hidden="true"
        style={{
          width: '46px',
          height: '46px',
          borderRadius: '50%',
          background: '#ffffff',
          color: '#155e52',
          display: 'grid',
          placeItems: 'center',
          fontWeight: 800,
          fontSize: '14px',
          border: '2px solid rgba(255,255,255,0.65)',
          boxShadow: '0 2px 8px rgba(0,0,0,0.16)',
          flexShrink: 0,
        }}
      >
        {initialsFor(name)}
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
          <h3
            style={{
              margin: 0,
              fontSize: '16px',
              fontWeight: 750,
              lineHeight: 1.2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {name}
          </h3>
          <span
            title={mode === 'ai' ? 'AI assistant active' : 'Counsellor connected'}
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: '#4ade80',
              boxShadow: '0 0 0 3px rgba(74, 222, 128, 0.16)',
              flexShrink: 0,
            }}
          />
        </div>
        <p
          style={{
            margin: '3px 0 0',
            color: 'rgba(255,255,255,0.76)',
            fontSize: '12px',
            lineHeight: 1.3,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {mode === 'ai' ? 'Nexus Student Enquiry Assistant' : 'Nexus Counsellor'}
          {meta ? ` • ${meta}` : ''}
        </p>
      </div>
    </div>

    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
      <span
        title="WhatsApp conversation"
        style={{
          width: '32px',
          height: '32px',
          borderRadius: '50%',
          display: 'grid',
          placeItems: 'center',
          color: 'rgba(255,255,255,0.82)',
        }}
      >
        <MessageCircle size={17} />
      </span>
      <span
        title="Candidate phone is shown in the conversation profile"
        style={{
          width: '32px',
          height: '32px',
          borderRadius: '50%',
          display: 'grid',
          placeItems: 'center',
          color: 'rgba(255,255,255,0.82)',
        }}
      >
        <Phone size={17} />
      </span>
      {actions}
      <span
        aria-hidden="true"
        style={{
          width: '30px',
          height: '30px',
          borderRadius: '50%',
          display: 'grid',
          placeItems: 'center',
          color: 'rgba(255,255,255,0.74)',
        }}
      >
        <MoreVertical size={17} />
      </span>
    </div>
  </header>
);

export default WhatsAppConversationHeader;
