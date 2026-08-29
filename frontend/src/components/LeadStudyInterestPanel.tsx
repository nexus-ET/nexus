import React from 'react';
import { CountryWithFlag } from '../utils/countryFlag';
import { formatStudyField, formatStudyProgram } from '../utils/studyChoiceIcons';

export interface LeadStudyInterestFields {
  name?: string | null;
  full_name?: string | null;
  preferred_country?: string | null;
  preferred_course?: string | null;
  target_program?: string | null;
  target_degree?: string | null;
  target_major?: string | null;
  study_interest_complete?: boolean;
  intake_complete?: boolean;
  stage?: string | null;
  english_test_scores?: string | null;
  test_scores?: string | null;
  wants_consultation_call?: boolean | null;
  consultation_session_date?: string | null;
  consultation_session_time?: string | null;
  assigned_counsellor_name?: string | null;
  appointment_status?: string | null;
}

interface LeadStudyInterestPanelProps {
  lead: LeadStudyInterestFields;
  compact?: boolean;
}

const LeadStudyInterestPanel: React.FC<LeadStudyInterestPanelProps> = ({ lead, compact = false }) => {
  const hasData = Boolean(
    lead.preferred_country ||
      lead.preferred_course ||
      lead.target_program ||
      lead.target_degree ||
      lead.target_major ||
      lead.english_test_scores ||
      lead.test_scores
  );

  if (!hasData) return null;

  const stage = (lead.stage || '').toUpperCase();
  const scheduled = Boolean(
    lead.consultation_session_date ||
      lead.consultation_session_time ||
      lead.appointment_status?.toLowerCase().includes('scheduled')
  );
  const closed = stage.includes('CLOSED') || stage.includes('ARCHIVE');
  const contacted = stage.includes('HANDOFF') || stage.includes('HUMAN') || scheduled || closed;
  const activePipelineStep = closed ? 3 : scheduled ? 2 : contacted ? 1 : 0;
  const pipelineSteps = ['New', 'Contacted', 'Scheduled', 'Closed'];
  const qualified = Boolean(lead.study_interest_complete || lead.intake_complete);
  const program = lead.target_degree || lead.target_program || '—';
  const field = lead.target_major || lead.preferred_course || '—';
  const test = lead.english_test_scores || lead.test_scores || 'Not taken yet';
  const callback =
    lead.wants_consultation_call === true
      ? lead.consultation_session_date || 'Requested'
      : lead.wants_consultation_call === false
        ? 'Not requested'
        : '—';

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '0.055em',
    textTransform: 'uppercase',
    color: '#6b778c',
    marginBottom: '3px',
  };

  const valueStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '13px',
    color: '#172033',
    fontWeight: 700,
    lineHeight: 1.3,
    overflowWrap: 'anywhere',
  };

  return (
    <div
      style={{
        padding: compact ? '10px 16px' : '14px',
        borderBottom: compact ? '1px solid #dce2e8' : undefined,
        background: '#f5f7f9',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          maxWidth: compact ? '780px' : undefined,
          margin: '0 auto',
          padding: '12px 14px',
          borderRadius: '14px',
          border: '1px solid #d5dce3',
          background: '#fbfcfd',
          boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
            marginBottom: '10px',
          }}
        >
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              borderRadius: '999px',
              gap: '6px',
              padding: '4px 10px',
              fontSize: '10px',
              letterSpacing: '0.055em',
              textTransform: 'uppercase',
              fontWeight: 800,
              color: qualified ? '#ffffff' : '#16685d',
              background: qualified ? '#287c6c' : '#e7f5f1',
              border: qualified ? '1px solid #287c6c' : '1px solid #a8d8cd',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                background: qualified ? '#58e294' : '#2f8a77',
              }}
            />
            {qualified ? 'Qualified student enquiry' : 'Student enquiry profile'}
          </span>
          <span
            style={{
              color: '#b45309',
              fontSize: '11px',
              fontWeight: 750,
              whiteSpace: 'nowrap',
            }}
          >
            {scheduled ? 'Follow-up scheduled' : contacted ? 'Follow-up active' : 'Follow-up pending'}
          </span>
        </div>

        <div
          style={{
            padding: '9px 10px',
            border: '1px solid #d8dee6',
            borderRadius: '11px',
            background: '#f2f4f7',
            marginBottom: '10px',
          }}
        >
          <span style={{ ...labelStyle, marginBottom: '6px' }}>Counselling pipeline</span>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '5px' }}>
            {pipelineSteps.map((step, index) => (
              <span
                key={step}
                style={{
                  padding: '5px 4px',
                  borderRadius: '7px',
                  textAlign: 'center',
                  fontSize: '10px',
                  fontWeight: 750,
                  color: index === activePipelineStep ? '#ffffff' : '#6b778c',
                  background: index === activePipelineStep ? '#246b60' : '#dce3ea',
                }}
              >
                {index === activePipelineStep ? '● ' : ''}
                {step}
              </span>
            ))}
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(145px, 1fr))',
            gap: '9px 16px',
          }}
        >
          <div>
            <span style={labelStyle}>Destination</span>
            <span style={{ ...valueStyle, color: '#216a5d' }}>
              {lead.preferred_country ? (
                <CountryWithFlag country={lead.preferred_country} />
              ) : (
                '—'
              )}
            </span>
          </div>
          <div>
            <span style={labelStyle}>Study level</span>
            <span style={valueStyle}>{program === '—' ? program : formatStudyProgram(program)}</span>
          </div>
          <div>
            <span style={labelStyle}>Program / field</span>
            <span style={{ ...valueStyle, color: '#216a5d' }}>
              {field === '—' ? field : formatStudyField(field)}
            </span>
          </div>
          <div>
            <span style={labelStyle}>English test</span>
            <span style={valueStyle}>{test}</span>
          </div>
          <div>
            <span style={labelStyle}>Callback request</span>
            <span style={{ ...valueStyle, color: '#216a5d' }}>{callback}</span>
          </div>
          <div>
            <span style={labelStyle}>Assigned counsellor</span>
            <span style={valueStyle}>{lead.assigned_counsellor_name || 'Not assigned'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LeadStudyInterestPanel;
