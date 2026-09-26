import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { allMainProcesses, pipelineLeadHref } from '../../utils/studentPipelineProcess';
import {
  processPage,
  processPageCurrent,
  processPager,
  processPagerList,
  processPageStep,
  processPageStepDisabled,
} from './prospectsLayout';

type PipelineProcessPagerProps = {
  currentPath: string;
  leadId: number | null;
};

export default function PipelineProcessPager({ currentPath, leadId }: PipelineProcessPagerProps) {
  const [searchParams] = useSearchParams();
  const searchKey = searchParams.toString();
  const processes = allMainProcesses();
  const currentIndex = processes.findIndex(item => item.path === currentPath);
  const previous = currentIndex > 0 ? processes[currentIndex - 1] : null;
  const next =
    currentIndex >= 0 && currentIndex < processes.length - 1 ? processes[currentIndex + 1] : null;

  return (
    <nav className={processPager} aria-label="Jump to process">
      {previous ? (
        <Link
          to={pipelineLeadHref(previous.path, { leadId, search: searchKey })}
          className={processPageStep}
          title={`Process ${previous.code} · ${previous.title}`}
          aria-label={`Previous process: ${previous.title}`}
        >
          <ChevronLeft size={16} strokeWidth={2.25} aria-hidden />
        </Link>
      ) : (
        <span className={`${processPageStep} ${processPageStepDisabled}`} aria-hidden>
          <ChevronLeft size={16} strokeWidth={2.25} />
        </span>
      )}

      <div className={processPagerList}>
        {processes.map(process => {
          const isCurrent = process.path === currentPath;
          const label = `Process ${process.code}: ${process.title}`;
          if (isCurrent) {
            return (
              <span
                key={process.path}
                className={processPageCurrent}
                title={label}
                aria-current="page"
              >
                {process.code}
              </span>
            );
          }
          return (
            <Link
              key={process.path}
              to={pipelineLeadHref(process.path, { leadId, search: searchKey })}
              className={processPage}
              title={label}
              aria-label={label}
            >
              {process.code}
            </Link>
          );
        })}
      </div>

      {next ? (
        <Link
          to={pipelineLeadHref(next.path, { leadId, search: searchKey })}
          className={processPageStep}
          title={`Process ${next.code} · ${next.title}`}
          aria-label={`Next process: ${next.title}`}
        >
          <ChevronRight size={16} strokeWidth={2.25} aria-hidden />
        </Link>
      ) : (
        <span className={`${processPageStep} ${processPageStepDisabled}`} aria-hidden>
          <ChevronRight size={16} strokeWidth={2.25} />
        </span>
      )}
    </nav>
  );
}
