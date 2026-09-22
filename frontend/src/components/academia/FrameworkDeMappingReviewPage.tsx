import FrameworkProgramMappingReviewPage from './FrameworkProgramMappingReviewPage';

const DE_CONFIG = {
  title: 'DE Program Mapping Review',
  description:
    'Suggestion queue for German (iso2=DE) programs that still need a major/sub-major mapping or major-only upgrade. Programs already committed in PEM are excluded. Dropdowns load the live catalog; apply writes the same table as Framework → Degrees.',
  embeddedDescription:
    'DE suggestion queue only — programs with a committed PEM are omitted. Dropdowns use the live majors/sub-majors catalog. Rebuild suggestions after catalog remaps or new DE scrapes if rows look stale.',
  suggestionsEndpoint: 'academia/de-program-mapping-suggestions',
  bulkApplyScope: {
    nz_scope_only: false,
    ca_scope_only: false,
    us_scope_only: false,
    de_scope_only: true,
  },
  loadingLabel: 'Loading DE mapping suggestions…',
  loadErrorLabel: 'Failed to load DE mapping suggestions',
};

const FrameworkDeMappingReviewPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => (
  <FrameworkProgramMappingReviewPage config={DE_CONFIG} embedded={embedded} />
);

export default FrameworkDeMappingReviewPage;

export type { ProgramMappingSuggestion as DeProgramMappingSuggestion } from './FrameworkProgramMappingReviewPage';
