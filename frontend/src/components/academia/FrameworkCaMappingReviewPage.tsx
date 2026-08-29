import FrameworkProgramMappingReviewPage from './FrameworkProgramMappingReviewPage';

const CA_CONFIG = {
  title: 'CA Program Mapping Review',
  description:
    'Suggestion queue for CA-24 programs (24 extracted Canadian institutions) that still need a major/sub-major mapping or major-only upgrade. Programs already committed in PEM are excluded. Dropdowns load the live catalog; apply writes the same table as Framework → Degrees.',
  embeddedDescription:
    'CA-24 suggestion queue only — programs with a committed PEM are omitted. Dropdowns use the live majors/sub-majors catalog. Rebuild suggestions after catalog remaps if rows look stale.',
  suggestionsEndpoint: 'academia/ca-program-mapping-suggestions',
  bulkApplyScope: { nz_scope_only: false, ca_scope_only: true },
  loadingLabel: 'Loading CA mapping suggestions…',
  loadErrorLabel: 'Failed to load CA mapping suggestions',
};

const FrameworkCaMappingReviewPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => (
  <FrameworkProgramMappingReviewPage config={CA_CONFIG} embedded={embedded} />
);

export default FrameworkCaMappingReviewPage;

export type { ProgramMappingSuggestion as CaProgramMappingSuggestion } from './FrameworkProgramMappingReviewPage';
