import { ArrowRight, ChevronLeft, ChevronRight } from 'lucide-react';
import { Fragment, useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useFlowxMaster } from '../../hooks/useFlowx';
import PipelineProcessPager from './PipelineProcessPager';
import {
  groupPipelineStripSegments,
  nextMainProcessAfter,
  pipelineLeadHref,
  pipelineSubprocessHref,
  previousMainProcessBefore,
  readPipelineSubprocess,
  usePipelineProcessNodes,
  type PipelineProcessNode,
  type StudentPipelineProcessConfig,
} from '../../utils/studentPipelineProcess';
import { parseLeadIdParam } from '../../utils/prospectsUrl';

type StripNode = PipelineProcessNode & {
  href?: string;
  navRole?: 'previous' | 'current' | 'next';
};

function nodeClassName(node: StripNode, activeCode: string): string {
  const nestClass =
    node.kind === 'subprocess' && node.nestRole === 'parent'
      ? ' is-nest-parent'
      : node.kind === 'subprocess' && node.nestRole === 'nested'
        ? ' is-nested'
        : '';
  const navClass = node.navRole === 'current' ? ' is-current-process' : '';
  return `prospects-toolbar__process-node${
    node.code === activeCode ? ' is-active' : ''
  }${node.kind === 'process' ? ' is-process' : ''}${navClass}${nestClass}`;
}

function MoveProcessArrowLink({
  node,
  href,
}: {
  node: StripNode;
  href: string;
}) {
  const isPrevious = node.navRole === 'previous';
  const Icon = isPrevious ? ChevronLeft : ChevronRight;
  return (
    <Link
      to={href}
      className={`prospects-toolbar__move-arrow is-${isPrevious ? 'previous' : 'next'}`}
      title={`Move to Process ${node.code} · ${node.title}`}
      aria-label={`Move to Process ${node.code}: ${node.title}`}
    >
      <Icon size={17} strokeWidth={2.5} aria-hidden />
      <Icon size={17} strokeWidth={2.5} aria-hidden />
    </Link>
  );
}

function ProcessNodeLink({
  node,
  activeCode,
  href,
}: {
  node: StripNode;
  activeCode: string;
  href: string;
}) {
  if (node.navRole === 'previous' || node.navRole === 'next') {
    return <MoveProcessArrowLink node={node} href={href} />;
  }
  const label = node.kind === 'process' ? `Process ${node.code}` : `Sub-Process ${node.code}`;
  return (
    <Link
      to={href}
      className={nodeClassName(node, activeCode)}
      title={`${label}: ${node.title}`}
      aria-current={node.navRole === 'current' || node.code === activeCode ? 'page' : undefined}
    >
      <p className="prospects-toolbar__subprocess-code">{label}</p>
      <p className="prospects-toolbar__subprocess-title">{node.title}</p>
    </Link>
  );
}

function FlowArrow({ nested }: { nested?: boolean }) {
  return (
    <ArrowRight
      size={16}
      strokeWidth={2.25}
      className={`prospects-toolbar__process-arrow${nested ? ' prospects-toolbar__process-arrow--nested' : ''}`}
      aria-hidden
    />
  );
}

function ProcessTerminus({ label, variant }: { label: 'Start' | 'End'; variant: 'start' | 'end' }) {
  return <span className={`prospects-toolbar__process-terminus is-${variant}`}>{label}</span>;
}

function useMidOverflow(enabled: boolean, revision: string | number) {
  const ref = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState({ left: false, right: false });

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) {
      setOverflow({ left: false, right: false });
      return;
    }
    const maxScroll = el.scrollWidth - el.clientWidth;
    setOverflow({
      left: el.scrollLeft > 4,
      right: maxScroll - el.scrollLeft > 4,
    });
  }, []);

  useLayoutEffect(() => {
    if (!enabled) {
      setOverflow({ left: false, right: false });
      return;
    }
    update();
    const frame = window.requestAnimationFrame(() => update());
    const el = ref.current;
    if (!el) {
      return () => window.cancelAnimationFrame(frame);
    }
    const observer = new ResizeObserver(update);
    observer.observe(el);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    el.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      el.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [enabled, revision, update]);

  const scrollByDir = useCallback((direction: -1 | 1) => {
    const el = ref.current;
    if (!el) return;
    const delta = Math.max(200, Math.round(el.clientWidth * 0.72)) * direction;
    el.scrollBy({ left: delta, behavior: 'smooth' });
  }, []);

  return { ref, overflow, scrollByDir };
}

export default function PipelineProcessStrip({
  config,
  activeCode: activeCodeProp,
}: {
  config: StudentPipelineProcessConfig;
  activeCode?: string;
}) {
  const { leadId: leadIdParam } = useParams<{ leadId?: string }>();
  const [searchParams] = useSearchParams();
  const leadId = parseLeadIdParam(leadIdParam);
  const activeCode = activeCodeProp || readPipelineSubprocess(searchParams, config.defaultSubprocess);
  const nodes = usePipelineProcessNodes(config);
  const masterQuery = useFlowxMaster();
  const previousProcess = useMemo(
    () => previousMainProcessBefore(config.stageKey, masterQuery.data?.stages),
    [config.stageKey, masterQuery.data?.stages]
  );
  const nextProcess = useMemo(
    () => nextMainProcessAfter(config.stageKey, masterQuery.data?.stages),
    [config.stageKey, masterQuery.data?.stages]
  );

  const searchKey = searchParams.toString();
  const previousChip: StripNode | null = useMemo(
    () =>
      previousProcess
        ? {
            code: previousProcess.code,
            title: previousProcess.title,
            kind: 'process',
            href: pipelineLeadHref(previousProcess.path, { leadId, search: searchKey }),
            navRole: 'previous',
          }
        : null,
    [previousProcess, leadId, searchKey]
  );
  const nextChip: StripNode | null = useMemo(
    () =>
      nextProcess
        ? {
            code: nextProcess.code,
            title: nextProcess.title,
            kind: 'process',
            href: pipelineLeadHref(nextProcess.path, { leadId, search: searchKey }),
            navRole: 'next',
          }
        : null,
    [nextProcess, leadId, searchKey]
  );
  const currentChip: StripNode | null = useMemo(() => {
    const currentProcess = nodes.find(node => node.kind === 'process');
    return currentProcess ? { ...currentProcess, navRole: 'current' } : null;
  }, [nodes]);
  const middleSegments = useMemo(
    () => groupPipelineStripSegments(nodes.filter(node => node.kind !== 'process')),
    [nodes]
  );

  const hrefFor = (node: StripNode) =>
    node.href ||
    pipelineSubprocessHref(node.kind === 'process' ? config.defaultSubprocess : node.code, {
      leadId,
      search: searchParams,
      basePath: config.path,
      defaultSubprocess: config.defaultSubprocess,
    });

  const showStart = !previousProcess;
  const showEnd = !nextProcess;
  const { ref: midRef, overflow: midOverflow, scrollByDir } = useMidOverflow(
    middleSegments.length > 0,
    `${middleSegments.length}:${activeCode}`
  );

  return (
    <div className="prospects-toolbar__subprocess prospects-toolbar__subprocess--flow">
      <div
        className="prospects-toolbar__process-flow"
        role="list"
        aria-label={`Process ${config.processNumber} flow`}
      >
        <div className="prospects-toolbar__process-flow-pin">
          {previousChip ? (
            <div className="prospects-toolbar__process-item" role="listitem">
              <ProcessNodeLink node={previousChip} activeCode={activeCode} href={hrefFor(previousChip)} />
            </div>
          ) : null}
        </div>

        <div className="prospects-toolbar__process-flow-center">
          {showStart ? (
            <div className="prospects-toolbar__process-item" role="listitem">
              <ProcessTerminus label="Start" variant="start" />
            </div>
          ) : null}
          {currentChip ? (
            <div className="prospects-toolbar__process-item" role="listitem">
              {showStart ? <FlowArrow /> : null}
              <ProcessNodeLink node={currentChip} activeCode={activeCode} href={hrefFor(currentChip)} />
            </div>
          ) : null}
        {middleSegments.length ? (
          <div
            className={`prospects-toolbar__process-flow-mid-wrap${
              midOverflow.left ? ' is-overflow-start' : ''
            }${midOverflow.right ? ' is-overflow-end' : ''}`}
          >
            {midOverflow.left ? (
              <>
                <span className="prospects-toolbar__process-flow-fade is-start" aria-hidden />
                <button
                  type="button"
                  className="prospects-toolbar__process-flow-chevron is-start"
                  aria-label="Scroll sub-processes left"
                  onClick={() => scrollByDir(-1)}
                >
                  <ChevronLeft size={16} strokeWidth={2.5} />
                </button>
              </>
            ) : null}
          <div ref={midRef} className="prospects-toolbar__process-flow-mid">
            {middleSegments.map(segment => {
              if (segment.type === 'item') {
                const node = segment.node as StripNode;
                return (
                  <div key={`${node.kind}-${node.code}`} className="prospects-toolbar__process-item" role="listitem">
                    <FlowArrow />
                    <ProcessNodeLink node={node} activeCode={activeCode} href={hrefFor(node)} />
                  </div>
                );
              }
              const parent = segment.nodes[0] as StripNode;
              return (
                <div key={`cluster-${parent.code}`} className="prospects-toolbar__process-item" role="listitem">
                  <FlowArrow />
                  <div
                    className="prospects-toolbar__process-cluster"
                    role="group"
                    aria-label={`Sub-process ${parent.code} with nested steps`}
                  >
                    {segment.nodes.map((node, nestIndex) => {
                      const stripNode = node as StripNode;
                      return (
                        <Fragment key={`${stripNode.kind}-${stripNode.code}`}>
                          {nestIndex > 0 ? <FlowArrow nested /> : null}
                          <ProcessNodeLink
                            node={stripNode}
                            activeCode={activeCode}
                            href={hrefFor(stripNode)}
                          />
                        </Fragment>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
            {midOverflow.right ? (
              <>
                <span className="prospects-toolbar__process-flow-fade is-end" aria-hidden />
                <button
                  type="button"
                  className="prospects-toolbar__process-flow-chevron is-end"
                  aria-label="Scroll sub-processes right"
                  onClick={() => scrollByDir(1)}
                >
                  <ChevronRight size={16} strokeWidth={2.5} />
                </button>
              </>
            ) : null}
          </div>
        ) : null}
          {showEnd ? (
            <div className="prospects-toolbar__process-item" role="listitem">
              <FlowArrow />
              <ProcessTerminus label="End" variant="end" />
            </div>
          ) : null}
        </div>

        <div className="prospects-toolbar__process-flow-pin">
          {nextChip ? (
            <div className="prospects-toolbar__process-item" role="listitem">
              <ProcessNodeLink node={nextChip} activeCode={activeCode} href={hrefFor(nextChip)} />
            </div>
          ) : null}
        </div>
      </div>
      <PipelineProcessPager currentPath={config.path} leadId={leadId} />
    </div>
  );
}
