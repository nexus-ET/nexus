/**
 * Mirrors the study-choice icon rules used by Meta WhatsApp list rows in
 * backend/app/services/meta_whatsapp_interactive.py.
 */
const STUDY_ICONS = ['🎓', '💻', '💼', '💰', '⚙️', '🩺', '🎨', '⚖️', '📚'] as const;

const normalizeStudyChoice = (value: string): string =>
  value
    .normalize('NFKD')
    .toLowerCase()
    .replace(/[_/\\-]+/g, ' ')
    .replace(/[^\p{L}\p{N}&+\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const withoutStudyIcon = (value: string): string => {
  const trimmed = value.trim();
  const icon = STUDY_ICONS.find(candidate => trimmed.startsWith(candidate));
  return icon ? trimmed.slice(icon.length).trimStart() : trimmed;
};

export const getStudyProgramIcon = (_value: string): string => '🎓';

export const getStudyFieldIcon = (value: string): string => {
  const normalized = normalizeStudyChoice(withoutStudyIcon(value));
  if (/(^| )(computer|data|software|information technology|it|ai|cyber)( |$)/.test(normalized)) {
    return '💻';
  }
  if (/(^| )(business|management|mba)( |$)/.test(normalized)) return '💼';
  if (/(^| )(finance|account|banking)( |$)/.test(normalized)) return '💰';
  if (/(^| )(engineer|engineering)( |$)/.test(normalized)) return '⚙️';
  if (/(^| )(health|medicine|medical|nursing)( |$)/.test(normalized)) return '🩺';
  if (/(^| )(art|arts|humanit|humanities|design)( |$)/.test(normalized)) return '🎨';
  if (/(^| )(law|legal)( |$)/.test(normalized)) return '⚖️';
  return '📚';
};

export const formatStudyProgram = (value: string): string => {
  const label = withoutStudyIcon(value);
  return label ? `${getStudyProgramIcon(label)} ${label}` : '';
};

export const formatStudyField = (value: string): string => {
  const label = withoutStudyIcon(value);
  return label ? `${getStudyFieldIcon(label)} ${label}` : '';
};
