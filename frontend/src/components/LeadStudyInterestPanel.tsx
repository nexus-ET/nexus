import React from 'react';

export interface LeadStudyInterestFields {
  preferred_country?: string | null;
  preferred_course?: string | null;
  target_program?: string | null;
  study_interest_complete?: boolean;
}

interface LeadStudyInterestPanelProps {
  lead: LeadStudyInterestFields;
  compact?: boolean;
}

const LeadStudyInterestPanel: React.FC<LeadStudyInterestPanelProps> = ({ lead, compact = false }) => {
  const hasData = Boolean(
    lead.preferred_country || lead.preferred_course || lead.target_program
  );

  if (!hasData) return null;

  const wrapperStyle: React.CSSProperties = compact
    ? {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: '10px',
        padding: '12px 14px',
        borderBottom: '1px solid #e2e8f0',
        background: '#f8fafc',
      }
    : {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
        gap: '12px',
        marginTop: '12px',
      };

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    color: '#64748b',
    marginBottom: '4px',
  };

  const valueStyle: React.CSSProperties = {
    fontSize: '14px',
    color: '#0f172a',
    fontWeight: 500,
  };

  return (
    <div style={wrapperStyle}>
      <div>
        <span style={labelStyle}>Target country</span>
        <span style={valueStyle}>{lead.preferred_country || '—'}</span>
      </div>
      <div>
        <span style={labelStyle}>Course</span>
        <span style={valueStyle}>{lead.preferred_course || '—'}</span>
      </div>
      <div>
        <span style={labelStyle}>Program</span>
        <span style={valueStyle}>{lead.target_program || lead.preferred_course || '—'}</span>
      </div>
      {lead.study_interest_complete ? (
        <div style={{ alignSelf: 'end' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              borderRadius: '999px',
              padding: '4px 10px',
              fontSize: '11px',
              fontWeight: 700,
              color: '#047857',
              background: '#ecfdf5',
              border: '1px solid #bbf7d0',
            }}
          >
            From Meta form
          </span>
        </div>
      ) : null}
    </div>
  );
};

export default LeadStudyInterestPanel;
