import { useMemo, useState } from 'react';
import { Outlet, useOutletContext } from 'react-router-dom';
import {
  FRAMEWORK_SECTION_PATH,
  FRAMEWORK_TABS,
  getAcademiaSectionLabel,
} from '../../config/academiaHubNav';
import AcademiaBreadcrumbs from '../../components/academia/AcademiaBreadcrumbs';
import AcademiaSectionTabs from '../../components/academia/AcademiaSectionTabs';

export type FrameworkSectionOutletContext = {
  frameworkTabActionsHost: HTMLDivElement | null;
};

const FrameworkSectionPage: React.FC = () => {
  const parentContext = useOutletContext<Record<string, unknown> | undefined>();
  const [tabActionsHost, setTabActionsHost] = useState<HTMLDivElement | null>(null);
  const outletContext = useMemo(
    () => ({
      ...parentContext,
      frameworkTabActionsHost: tabActionsHost,
    }),
    [parentContext, tabActionsHost]
  );

  return (
    <div className="space-y-4">
      <AcademiaBreadcrumbs
        items={[
          { label: 'Academia Hub', path: '/academia' },
          { label: getAcademiaSectionLabel('framework'), path: FRAMEWORK_SECTION_PATH },
        ]}
      />
      <div className="rounded-2xl border border-border-subtle bg-card shadow-sm">
        <div className="border-b border-border-subtle px-6 py-4">
          <h2 className="text-xl font-bold text-text-main">Academic Framework</h2>
          <p className="text-sm text-text-muted">
            Level &gt; Program &gt; Major / Discipline &gt; Course — academic mapping for student
            filtering and admissions matching.
          </p>
        </div>
        <div className="px-6 pt-4">
          <AcademiaSectionTabs
            tabs={FRAMEWORK_TABS}
            actions={<div ref={setTabActionsHost} className="flex items-center" />}
          />
        </div>
        <div className="p-6 pt-4">
          <Outlet context={outletContext} />
        </div>
      </div>
    </div>
  );
};

export default FrameworkSectionPage;
