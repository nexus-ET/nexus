import { useMemo } from 'react';
import { STUDENT_PIPELINE_NAV } from '../config/studentPipelineNav';
import { useFlowxMaster } from '../hooks/useFlowx';
import type { FlowxTaskTemplate } from '../types/flowx';

export const PIPELINE_SUBPROCESS_PARAM = 'subprocess';

export type PipelineNestRole = 'leaf' | 'parent' | 'nested';

export type PipelineProcessNode = {
  code: string;
  title: string;
  kind: 'process' | 'subprocess';
  /** Sub-process only: leaf sibling, parent that owns nests, or nested child. */
  nestRole?: PipelineNestRole;
};

export type PipelineStripSegment =
  | { type: 'item'; node: PipelineProcessNode }
  | { type: 'cluster'; nodes: PipelineProcessNode[] };

export type StudentPipelineProcessConfig = {
  path: string;
  stageKey: string;
  processNumber: number;
  defaultSubprocess: string;
  fallbackNodes: PipelineProcessNode[];
  titleAliases?: Record<string, string>;
};

const FLOWX_STAGE_TO_PIPELINE: Record<string, string> = {
  counselling: '/students/counselling',
  college_finding: '/students/college-finding',
  document_submission: '/students/document-readiness',
  admission_processing: '/students/admission-processing',
  visa_processing: '/students/visa-processing',
  predeparture_travel: '/students/pre-departure-travel',
  landing: '/students/landing',
};

export const STUDENT_PIPELINE_PROCESS_BY_PATH: Record<string, StudentPipelineProcessConfig> = {
  '/students/counselling': {
    path: '/students/counselling',
    stageKey: 'counselling',
    processNumber: 1,
    defaultSubprocess: '1.1',
    titleAliases: {
      'intake session': 'Initial Profile & Background Assessment',
    },
    fallbackNodes: [
      { code: '1', title: 'Counselling', kind: 'process' },
      { code: '1.1', title: 'Initial Profile & Background Assessment', kind: 'subprocess' },
      { code: '1.2', title: 'Profile & goals capture', kind: 'subprocess' },
      { code: '1.3', title: 'Destination shortlist discussion', kind: 'subprocess' },
    ],
  },
  '/students/college-finding': {
    path: '/students/college-finding',
    stageKey: 'college_finding',
    processNumber: 2,
    defaultSubprocess: '2.1',
    fallbackNodes: [
      { code: '2', title: 'College Finding', kind: 'process' },
      { code: '2.1', title: 'Shortlist target universities', kind: 'subprocess' },
      { code: '2.2', title: 'Confirm program fit', kind: 'subprocess' },
      { code: '2.3', title: 'Submit university enquiry', kind: 'subprocess' },
    ],
  },
  '/students/document-readiness': {
    path: '/students/document-readiness',
    stageKey: 'document_submission',
    processNumber: 3,
    defaultSubprocess: '3.1',
    fallbackNodes: [
      { code: '3', title: 'Document Readiness', kind: 'process' },
      { code: '3.1', title: 'Collect academic transcripts', kind: 'subprocess' },
      { code: '3.2', title: 'Prepare SOP draft', kind: 'subprocess' },
      { code: '3.3', title: 'Gather recommendation letters', kind: 'subprocess' },
    ],
  },
  '/students/admission-processing': {
    path: '/students/admission-processing',
    stageKey: 'admission_processing',
    processNumber: 4,
    defaultSubprocess: '4.1',
    titleAliases: {
      'submit university enquiry': 'Applications',
    },
    fallbackNodes: [
      { code: '4', title: 'Admission Processing', kind: 'process' },
      { code: '4.1', title: 'Applications', kind: 'subprocess' },
      { code: '4.2', title: 'Confirm program fit', kind: 'subprocess' },
      { code: '4.3', title: 'Collect academic transcripts', kind: 'subprocess' },
    ],
  },
  '/students/visa-processing': {
    path: '/students/visa-processing',
    stageKey: 'visa_processing',
    processNumber: 5,
    defaultSubprocess: '5.1',
    fallbackNodes: [
      { code: '5', title: 'Visa Processing', kind: 'process' },
      { code: '5.1', title: 'Proof of funds checklist', kind: 'subprocess' },
      { code: '5.2', title: 'Visa document pack', kind: 'subprocess' },
      { code: '5.3', title: 'Fee payment plan', kind: 'subprocess' },
    ],
  },
  '/students/pre-departure-travel': {
    path: '/students/pre-departure-travel',
    stageKey: 'predeparture_travel',
    processNumber: 6,
    defaultSubprocess: '6.1',
    fallbackNodes: [
      { code: '6', title: 'Pre-Departure & Travel', kind: 'process' },
      { code: '6.1', title: 'Visa document pack', kind: 'subprocess' },
      { code: '6.2', title: 'Fee payment plan', kind: 'subprocess' },
      { code: '6.3', title: 'Travel booking', kind: 'subprocess' },
    ],
  },
  '/students/landing': {
    path: '/students/landing',
    stageKey: 'landing',
    processNumber: 7,
    defaultSubprocess: '7.1',
    fallbackNodes: [
      { code: '7', title: 'Landing', kind: 'process' },
      { code: '7.1', title: 'Airport arrival', kind: 'subprocess' },
      { code: '7.2', title: 'Accommodation check-in', kind: 'subprocess' },
      { code: '7.3', title: 'Local orientation', kind: 'subprocess' },
    ],
  },
};

export function pipelineProcessConfig(basePath: string): StudentPipelineProcessConfig | null {
  return STUDENT_PIPELINE_PROCESS_BY_PATH[basePath] || null;
}

export function hasPipelineWorkspace(basePath: string): boolean {
  return Boolean(pipelineProcessConfig(basePath));
}

export function defaultSubprocessForBasePath(basePath: string): string | null {
  return pipelineProcessConfig(basePath)?.defaultSubprocess ?? null;
}

export function isDefaultPipelineSubprocess(
  code: string | null | undefined,
  defaultCode: string | null | undefined
): boolean {
  const normalized = (code || '').trim();
  const fallback = (defaultCode || '').trim();
  if (!normalized) return true;
  if (!fallback) return false;
  if (normalized === fallback) return true;
  return normalized === fallback.split('.')[0];
}

export function isAdmissionApplicationsSubprocess(
  code: string | null | undefined,
  config?: StudentPipelineProcessConfig | null
): boolean {
  if (!config || config.path !== '/students/admission-processing') return false;
  return isDefaultPipelineSubprocess(code, config.defaultSubprocess);
}

export function readPipelineSubprocess(
  search: string | URLSearchParams,
  defaultCode: string
): string {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;
  const raw = (params.get(PIPELINE_SUBPROCESS_PARAM) || '').trim();
  if (!raw || isDefaultPipelineSubprocess(raw, defaultCode)) return defaultCode;
  return raw;
}

export function pipelineLeadHref(
  path: string,
  options?: {
    leadId?: number | string | null;
    search?: string | URLSearchParams;
  }
): string {
  const params = new URLSearchParams(
    typeof options?.search === 'string'
      ? options.search
      : options?.search
        ? options.search.toString()
        : ''
  );
  params.delete(PIPELINE_SUBPROCESS_PARAM);
  const query = params.toString();
  const nextPath = options?.leadId ? `${path}/${options.leadId}` : path;
  return query ? `${nextPath}?${query}` : nextPath;
}

export function pipelineSubprocessHref(
  code: string,
  options: {
    leadId?: number | string | null;
    search?: string | URLSearchParams;
    basePath: string;
    defaultSubprocess: string;
  }
): string {
  const params = new URLSearchParams(
    typeof options.search === 'string'
      ? options.search
      : options.search
        ? options.search.toString()
        : ''
  );
  if (isDefaultPipelineSubprocess(code, options.defaultSubprocess)) {
    params.delete(PIPELINE_SUBPROCESS_PARAM);
  } else {
    params.set(PIPELINE_SUBPROCESS_PARAM, code.trim());
  }
  const query = params.toString();
  const path = options.leadId ? `${options.basePath}/${options.leadId}` : options.basePath;
  return query ? `${path}?${query}` : path;
}

type PipelineStageMeta = {
  stage_key: string;
  label: string;
  is_hidden?: boolean;
  position_index: number;
};

export type MainProcessNavItem = { code: string; title: string; path: string };

export function allMainProcesses(): MainProcessNavItem[] {
  return STUDENT_PIPELINE_NAV.map((item, index) => ({
    code: String(index + 1),
    title: item.label.replace(/^\d+\s+/, ''),
    path: item.path,
  }));
}

type AdjacentMainProcess = MainProcessNavItem;

function adjacentMainProcess(
  stageKey: string,
  stages: PipelineStageMeta[] | null | undefined,
  direction: 1 | -1
): AdjacentMainProcess | null {
  const visible = [...(stages ?? [])]
    .filter(stage => !stage.is_hidden)
    .sort((a, b) => a.position_index - b.position_index);
  const currentIndex = visible.findIndex(stage => stage.stage_key === stageKey);
  const currentPath = FLOWX_STAGE_TO_PIPELINE[stageKey];
  const currentNavIndex = currentPath
    ? STUDENT_PIPELINE_NAV.findIndex(item => item.path === currentPath)
    : -1;

  if (currentIndex >= 0) {
    for (
      let index = currentIndex + direction;
      index >= 0 && index < visible.length;
      index += direction
    ) {
      const stage = visible[index];
      const path = FLOWX_STAGE_TO_PIPELINE[stage.stage_key];
      if (!path || path === currentPath) continue;
      const pipelineIndex = STUDENT_PIPELINE_NAV.findIndex(item => item.path === path);
      return {
        code: String(pipelineIndex >= 0 ? pipelineIndex + 1 : currentNavIndex + 1 + direction),
        title: stage.label?.trim() || path,
        path,
      };
    }
  }

  if (currentNavIndex < 0) return null;
  const fallbackIndex = currentNavIndex + direction;
  const fallback = STUDENT_PIPELINE_NAV[fallbackIndex];
  if (!fallback) return null;
  return {
    code: String(fallbackIndex + 1),
    title: fallback.label.replace(/^\d+\s+/, ''),
    path: fallback.path,
  };
}

export function nextMainProcessAfter(
  stageKey: string,
  stages?: PipelineStageMeta[] | null
): AdjacentMainProcess | null {
  return adjacentMainProcess(stageKey, stages, 1);
}

export function previousMainProcessBefore(
  stageKey: string,
  stages?: PipelineStageMeta[] | null
): AdjacentMainProcess | null {
  return adjacentMainProcess(stageKey, stages, -1);
}

function sortedNestChildren<T extends { position_index: number; title: string }>(
  children: T[] | undefined | null
): T[] {
  return [...(children ?? [])].sort((a, b) => {
    if (a.position_index !== b.position_index) return a.position_index - b.position_index;
    return a.title.localeCompare(b.title);
  });
}

function displayTitle(title: string, aliases?: Record<string, string>): string {
  const alias = aliases?.[title.trim().toLowerCase()];
  return alias || title.trim();
}

function orderedTopBricks(stage: {
  bricks?: FlowxTaskTemplate[];
  tracks?: { task_templates?: FlowxTaskTemplate[] }[];
}): FlowxTaskTemplate[] {
  const bricks = stage.bricks ?? stage.tracks?.flatMap(track => track.task_templates || []) ?? [];
  return [...bricks]
    .filter(brick => !brick.parent_template_id)
    .sort((a, b) => {
      if (a.position_index !== b.position_index) return a.position_index - b.position_index;
      return a.title.localeCompare(b.title);
    });
}

function flattenSubprocesses(
  bricks: FlowxTaskTemplate[],
  parentCode: string,
  aliases?: Record<string, string>,
  depth = 1
): PipelineProcessNode[] {
  const nodes: PipelineProcessNode[] = [];
  bricks.forEach((brick, index) => {
    const code = `${parentCode}.${index + 1}`;
    const children = sortedNestChildren(brick.children);
    const nestRole: PipelineNestRole = depth >= 2 ? 'nested' : children.length ? 'parent' : 'leaf';
    nodes.push({
      code,
      title: displayTitle(brick.title || `Step ${code}`, aliases),
      kind: 'subprocess',
      nestRole,
    });
    if (children.length) nodes.push(...flattenSubprocesses(children, code, aliases, depth + 1));
  });
  return nodes;
}

export function isNestedUnder(code: string, parentCode: string): boolean {
  return Boolean(code && parentCode && code.startsWith(`${parentCode}.`));
}

/** Wrap a parent sub-process and its flattened descendants into one cluster rail. */
export function groupPipelineStripSegments(nodes: PipelineProcessNode[]): PipelineStripSegment[] {
  const segments: PipelineStripSegment[] = [];
  let index = 0;
  while (index < nodes.length) {
    const node = nodes[index];
    if (node.kind === 'process' || node.nestRole !== 'parent') {
      segments.push({ type: 'item', node });
      index += 1;
      continue;
    }
    const cluster = [node];
    index += 1;
    while (index < nodes.length && isNestedUnder(nodes[index].code, node.code)) {
      cluster.push(nodes[index]);
      index += 1;
    }
    segments.push(cluster.length > 1 ? { type: 'cluster', nodes: cluster } : { type: 'item', node });
  }
  return segments;
}

export function usePipelineProcessNodes(config: StudentPipelineProcessConfig): PipelineProcessNode[] {
  const masterQuery = useFlowxMaster();

  return useMemo((): PipelineProcessNode[] => {
    const stages = [...(masterQuery.data?.stages ?? [])]
      .filter(stage => !stage.is_hidden)
      .sort((a, b) => a.position_index - b.position_index);
    const stage =
      stages.find(item => item.stage_key === config.stageKey) ||
      stages[config.processNumber - 1] ||
      null;
    if (!stage) return config.fallbackNodes;

    const process: PipelineProcessNode = {
      code: String(config.processNumber),
      title: stage.label?.trim() || config.fallbackNodes[0]?.title || `Process ${config.processNumber}`,
      kind: 'process',
    };
    const children = flattenSubprocesses(
      orderedTopBricks(stage),
      String(config.processNumber),
      config.titleAliases
    );
    if (!children.length) return config.fallbackNodes;
    return [process, ...children];
  }, [config, masterQuery.data?.stages]);
}
