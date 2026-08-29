import React from 'react';
import { CountryWithFlag } from '../utils/countryFlag';

export interface WhatsAppIntakeOption {
  id: string;
  label: string;
  description?: string;
  selected?: boolean;
}

interface WhatsAppIntakeOptionTrayProps {
  step?: string;
  stepLabel?: string;
  options?: WhatsAppIntakeOption[];
}

function optionLabelWithIcon(step: string, label: string): string {
  const normalizedStep = step.trim().toUpperCase();
  if (normalizedStep === 'TARGET_DEGREE') return `🎓 ${label}`;
  if (normalizedStep !== 'TARGET_MAJOR') return label;

  const lowered = label.toLowerCase();
  if (/(computer|data|software|\bai\b)/.test(lowered)) return `💻 ${label}`;
  if (/(business|management|mba)/.test(lowered)) return `💼 ${label}`;
  if (/(finance|account)/.test(lowered)) return `💰 ${label}`;
  if (/engineer/.test(lowered)) return `⚙️ ${label}`;
  if (/(health|medicine|medical)/.test(lowered)) return `🩺 ${label}`;
  if (/(art|humanit|design)/.test(lowered)) return `🎨 ${label}`;
  if (/law/.test(lowered)) return `⚖️ ${label}`;
  return `📚 ${label}`;
}

const WhatsAppIntakeOptionTray: React.FC<WhatsAppIntakeOptionTrayProps> = ({
  step,
  stepLabel,
  options = [],
}) => {
  if (!step || step === 'COMPLETE' || options.length === 0) return null;
  const isCountryStep = step.trim().toUpperCase() === 'TARGET_COUNTRY';

  return (
    <section
      aria-label={`WhatsApp options for ${stepLabel || step}`}
      style={{
        padding: '9px 16px 11px',
        background: '#f5f6f7',
        borderTop: '1px solid #d9dee3',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          marginBottom: '7px',
        }}
      >
        <span
          style={{
            color: '#7a8490',
            fontSize: '9px',
            fontWeight: 800,
            letterSpacing: '0.09em',
          }}
        >
          SELECT OPTION TO PROCEED
        </span>
        <span
          style={{
            color: '#216a5d',
            fontSize: '10px',
            fontWeight: 750,
          }}
        >
          {stepLabel || step.replaceAll('_', ' ').toLowerCase()}
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '7px' }}>
        {options.map(option => (
          <span
            key={option.id}
            title={option.description || option.label}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              minHeight: '30px',
              padding: '5px 11px',
              borderRadius: '999px',
              border: option.selected ? '1px solid #155e52' : '1px solid #4c766f',
              background: option.selected ? '#155e52' : '#ffffff',
              color: option.selected ? '#ffffff' : '#244b45',
              fontSize: '12px',
              fontWeight: 700,
              lineHeight: 1.2,
              boxShadow: option.selected ? '0 2px 6px rgba(21,94,82,0.2)' : 'none',
            }}
          >
            {isCountryStep ? (
              <CountryWithFlag country={option.label || option.id} />
            ) : (
              optionLabelWithIcon(step, option.label)
            )}
          </span>
        ))}
      </div>
    </section>
  );
};

export default WhatsAppIntakeOptionTray;
