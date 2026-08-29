import FrameworkProgramMappingReviewPage from './FrameworkProgramMappingReviewPage';

const NZ_CONFIG = {
  title: 'NZ Program Mapping Review',
  description:
    'Suggestion queue for NZ programs that still need a major/sub-major mapping or major-only upgrade. Programs already committed in PEM are excluded. Dropdowns load the live catalog; apply writes the same table as Framework → Degrees.',
  embeddedDescription:
    'Suggestion queue only — programs with a committed PEM are omitted. Dropdowns use the live majors/sub-majors catalog. After catalog remaps, rebuild suggestions if rows look stale.',
  suggestionsEndpoint: 'academia/nz-program-mapping-suggestions',
  bulkApplyScope: { nz_scope_only: true, ca_scope_only: false },
  loadingLabel: 'Loading NZ mapping suggestions…',
  loadErrorLabel: 'Failed to load NZ mapping suggestions',
};

const FrameworkNzMappingReviewPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => (
  <FrameworkProgramMappingReviewPage config={NZ_CONFIG} embedded={embedded} />
);

export default FrameworkNzMappingReviewPage;

export type { ProgramMappingSuggestion as NzProgramMappingSuggestion } from './FrameworkProgramMappingReviewPage';
