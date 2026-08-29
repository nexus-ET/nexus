import {
  PIPELINE_SUBPROCESS_PARAM,
  defaultSubprocessForBasePath,
  isDefaultPipelineSubprocess,
  nextMainProcessAfter,
  pipelineLeadHref,
  pipelineProcessConfig,
  pipelineSubprocessHref,
  readPipelineSubprocess,
  type PipelineProcessNode,
} from './studentPipelineProcess';

export const COUNSELLING_BASE_PATH = '/students/counselling';
export const COUNSELLING_SUBPROCESS_PARAM = PIPELINE_SUBPROCESS_PARAM;
export const COUNSELLING_INTAKE_SUBPROCESS = '1.1';
export const COUNSELLING_BILLING_SUBPROCESS = '1.2';
export const COUNSELLING_CREDENTIALS_SUBPROCESS = '1.3';

export type { PipelineProcessNode as CounsellingProcessNode };

export function pipelineProcessHref(
  path: string,
  options?: {
    leadId?: number | string | null;
    search?: string | URLSearchParams;
  }
): string {
  return pipelineLeadHref(path, options);
}

export function nextMainProcessAfterCounselling(stages?: Array<{
  stage_key: string;
  label: string;
  is_hidden?: boolean;
  position_index: number;
}> | null): { code: string; title: string; path: string } {
  return (
    nextMainProcessAfter('counselling', stages) || {
      code: '2',
      title: 'College Finding',
      path: '/students/college-finding',
    }
  );
}

export function readCounsellingSubprocess(search: string | URLSearchParams): string {
  return readPipelineSubprocess(search, COUNSELLING_INTAKE_SUBPROCESS);
}

export function isCounsellingIntakeSubprocess(code: string | null | undefined): boolean {
  return isDefaultPipelineSubprocess(code, COUNSELLING_INTAKE_SUBPROCESS);
}

export function isCounsellingBillingSubprocess(code: string | null | undefined): boolean {
  return (code || '').trim() === COUNSELLING_BILLING_SUBPROCESS;
}

export function isCounsellingCredentialsSubprocess(code: string | null | undefined): boolean {
  return (code || '').trim() === COUNSELLING_CREDENTIALS_SUBPROCESS;
}

export function counsellingSubprocessHref(
  code: string,
  options?: {
    leadId?: number | string | null;
    search?: string | URLSearchParams;
    basePath?: string;
  }
): string {
  const basePath = options?.basePath || COUNSELLING_BASE_PATH;
  return pipelineSubprocessHref(code, {
    leadId: options?.leadId,
    search: options?.search,
    basePath,
    defaultSubprocess: defaultSubprocessForBasePath(basePath) || COUNSELLING_INTAKE_SUBPROCESS,
  });
}

export { pipelineProcessConfig };
