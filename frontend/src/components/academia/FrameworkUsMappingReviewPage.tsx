import FrameworkProgramMappingReviewPage from './FrameworkProgramMappingReviewPage';

const US_CONFIG = {
  title: 'US Program Mapping Review',
  description:
    'Suggestion queue for US programs that still need a major/sub-major mapping or major-only upgrade. Programs already committed in PEM are excluded. Dropdowns load the live catalog; apply writes the same table as Framework → Degrees.',
  embeddedDescription:
    'US suggestion queue only — programs with a committed PEM are omitted. Dropdowns use the live majors/sub-majors catalog. Rebuild suggestions after catalog remaps or new US scrapes if rows look stale.',
  suggestionsEndpoint: 'academia/us-program-mapping-suggestions',
  bulkApplyScope: { nz_scope_only: false, ca_scope_only: false, us_scope_only: true },
  loadingLabel: 'Loading US mapping suggestions…',
  loadErrorLabel: 'Failed to load US mapping suggestions',
};

const FrameworkUsMappingReviewPage: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => (
  <FrameworkProgramMappingReviewPage config={US_CONFIG} embedded={embedded} />
);

export default FrameworkUsMappingReviewPage;

export type { ProgramMappingSuggestion as UsProgramMappingSuggestion } from './FrameworkProgramMappingReviewPage';
