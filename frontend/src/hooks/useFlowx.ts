import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../utils/api';
import type {
  FlowxApplicationLookups,
  FlowxBoardResponse,
  FlowxCountryDestinations,
  FlowxCountryDetail,
  FlowxCountryGeography,
  FlowxCountrySummary,
  FlowxEnrollment,
  FlowxEnrollmentListItem,
  FlowxKanbanStatus,
  FlowxOpsOverview,
  FlowxPathway,
  FlowxStageKey,
} from '../types/flowx';

function toQuery(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === '') return;
    search.set(key, String(value));
  });
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export function useFlowxCountries() {
  return useQuery({
    queryKey: ['flowx-countries'],
    queryFn: () => apiFetch<FlowxCountrySummary[]>('flowx/countries'),
    staleTime: 30_000,
  });
}

export function useFlowxOpsOverview() {
  return useQuery({
    queryKey: ['flowx-ops-overview'],
    queryFn: () => apiFetch<FlowxOpsOverview>('flowx/ops/overview'),
    staleTime: 20_000,
    refetchInterval: 60_000,
  });
}

export function useFlowxMaster() {
  return useQuery({
    queryKey: ['flowx-master'],
    queryFn: () => apiFetch<FlowxCountryDetail>('flowx/master'),
    staleTime: 15_000,
  });
}

function useMasterMutationInvalidation() {
  const qc = useQueryClient();
  return (data?: FlowxCountryDetail) => {
    if (data) qc.setQueryData(['flowx-master'], data);
    qc.invalidateQueries({ queryKey: ['flowx-master'] });
    qc.invalidateQueries({ queryKey: ['flowx-country'] });
    qc.invalidateQueries({ queryKey: ['flowx-countries'] });
    qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
    qc.invalidateQueries({ queryKey: ['flowx-board'] });
  };
}

export function useMasterRenameProcessLabel() {
  const invalidate = useMasterMutationInvalidation();
  return useMutation({
    mutationFn: (payload: { stage_key: FlowxStageKey; label: string }) =>
      apiFetch<FlowxCountryDetail>('flowx/master/process-labels', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: invalidate,
  });
}

export function useMasterAddTemplate() {
  const invalidate = useMasterMutationInvalidation();
  return useMutation({
    mutationFn: (payload: {
      track_id: string;
      title: string;
      description?: string;
      action_steps?: string[];
      parent_template_id?: string | null;
    }) =>
      apiFetch<FlowxCountryDetail>(`flowx/master/tracks/${payload.track_id}/templates`, {
        method: 'POST',
        body: JSON.stringify({
          title: payload.title,
          description: payload.description,
          action_steps: payload.action_steps ?? [],
          parent_template_id: payload.parent_template_id,
        }),
      }),
    onSuccess: invalidate,
  });
}

export function useMasterRenameTemplate() {
  const invalidate = useMasterMutationInvalidation();
  return useMutation({
    mutationFn: (payload: {
      template_id: string;
      title?: string;
      description?: string | null;
      action_steps?: string[];
    }) =>
      apiFetch<FlowxCountryDetail>(`flowx/master/templates/${payload.template_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: payload.title,
          description: payload.description,
          action_steps: payload.action_steps,
        }),
      }),
    onSuccess: invalidate,
  });
}

export function useMasterDeleteTemplate() {
  const invalidate = useMasterMutationInvalidation();
  return useMutation({
    mutationFn: (template_id: string) =>
      apiFetch<FlowxCountryDetail>(`flowx/master/templates/${template_id}`, {
        method: 'DELETE',
      }),
    onSuccess: invalidate,
  });
}

export function useFlowxCountry(iso2: string | null) {
  return useQuery({
    queryKey: ['flowx-country', iso2],
    queryFn: () => apiFetch<FlowxCountryDetail>(`flowx/countries/${iso2}`),
    enabled: Boolean(iso2),
    staleTime: 15_000,
  });
}

export function useEnsureFlowxCountry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (iso2: string) =>
      apiFetch<FlowxCountryDetail>(`flowx/countries/${iso2}/ensure`, { method: 'POST' }),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['flowx-countries'] });
      qc.setQueryData(['flowx-country', data.country_iso2], data);
    },
  });
}

export function useRemoveFlowxCountry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: string | { iso2: string; force?: boolean }) => {
      const iso2 = typeof payload === 'string' ? payload : payload.iso2;
      const force = typeof payload === 'string' ? false : Boolean(payload.force);
      return apiFetch<FlowxCountrySummary>(
        `flowx/countries/${iso2}${force ? '?force=true' : ''}`,
        { method: 'DELETE' }
      );
    },
    onSuccess: (_data, payload) => {
      const iso2 = typeof payload === 'string' ? payload : payload.iso2;
      qc.invalidateQueries({ queryKey: ['flowx-countries'] });
      qc.removeQueries({ queryKey: ['flowx-country', iso2] });
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
    },
  });
}

export function useEnrollFlowxStudent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      iso2: string;
      lead_id: number;
      institution_id?: number | null;
      college_id?: number | null;
      campus_id?: number | null;
      level_id?: number | null;
      qualification_program_id?: string | null;
      intake_id?: number | null;
      pathway_type?: string | null;
      pathway_name?: string | null;
      custom_pathway_name?: string | null;
      portal_url?: string | null;
      portal_username?: string | null;
      portal_password_hint?: string | null;
      institutional_app_id?: string | null;
      application_status?: string | null;
      fee_status?: string | null;
      fee_amount?: number | null;
      fee_currency?: string | null;
      internal_target_date?: string | null;
      official_deadline?: string | null;
    }) =>
      apiFetch<FlowxEnrollment>(`flowx/countries/${payload.iso2}/enroll`, {
        method: 'POST',
        body: JSON.stringify({
          lead_id: payload.lead_id,
          institution_id: payload.institution_id ?? null,
          college_id: payload.college_id ?? null,
          campus_id: payload.campus_id ?? null,
          level_id: payload.level_id ?? null,
          qualification_program_id: payload.qualification_program_id ?? null,
          intake_id: payload.intake_id ?? null,
          pathway_type: payload.pathway_type ?? null,
          pathway_name: payload.pathway_name ?? null,
          custom_pathway_name: payload.custom_pathway_name ?? null,
          portal_url: payload.portal_url ?? null,
          portal_username: payload.portal_username ?? null,
          portal_password_hint: payload.portal_password_hint ?? null,
          institutional_app_id: payload.institutional_app_id ?? null,
          application_status: payload.application_status ?? 'drafting',
          fee_status: payload.fee_status ?? 'not_required',
          fee_amount: payload.fee_amount ?? null,
          fee_currency: payload.fee_currency ?? 'USD',
          internal_target_date: payload.internal_target_date ?? null,
          official_deadline: payload.official_deadline ?? null,
        }),
      }),
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
      qc.invalidateQueries({ queryKey: ['flowx-countries'] });
      qc.invalidateQueries({ queryKey: ['flowx-pathways'] });
      qc.setQueryData(['flowx-enrollment', data.id], data);
    },
  });
}

export function useFlowxCountryDestinations(
  iso2: string | null,
  filters: { state_id?: number; city_id?: number } = {}
) {
  return useQuery({
    queryKey: ['flowx-destinations', iso2, filters.state_id ?? null, filters.city_id ?? null],
    queryFn: () =>
      apiFetch<FlowxCountryDestinations>(
        `flowx/countries/${iso2}/destinations${toQuery({
          state_id: filters.state_id,
          city_id: filters.city_id,
        })}`
      ),
    enabled: Boolean(iso2),
    staleTime: 60_000,
  });
}

export function useFlowxCountryGeography(iso2: string | null, stateId?: number | null) {
  return useQuery({
    queryKey: ['flowx-geography', iso2, stateId ?? null],
    queryFn: () =>
      apiFetch<FlowxCountryGeography>(
        `flowx/countries/${iso2}/geography${toQuery({
          state_id: stateId || undefined,
        })}`
      ),
    enabled: Boolean(iso2),
    staleTime: 60_000,
  });
}

export function useFlowxApplicationLookups(query: {
  institution_id?: number;
  campus_id?: number;
  college_id?: number;
  level_id?: number;
} = {}) {
  return useQuery({
    queryKey: ['flowx-application-lookups', query],
    queryFn: () =>
      apiFetch<FlowxApplicationLookups>(
        `flowx/application-lookups${toQuery({
          institution_id: query.institution_id,
          campus_id: query.campus_id,
          college_id: query.college_id,
          level_id: query.level_id,
        })}`
      ),
    staleTime: 30_000,
  });
}

export function useFlowxPathways(pathwayType?: string | null) {
  return useQuery({
    queryKey: ['flowx-pathways', pathwayType ?? ''],
    queryFn: () =>
      apiFetch<FlowxPathway[]>(
        `flowx/pathways${toQuery({ pathway_type: pathwayType || undefined })}`
      ),
    staleTime: 60_000,
  });
}

export function useFlowxEnrollments(query: {
  country?: string;
  status?: string;
  q?: string;
  lead_id?: number;
} = {}) {
  return useQuery({
    queryKey: ['flowx-enrollments', query],
    queryFn: () =>
      apiFetch<{ items: FlowxEnrollmentListItem[]; total: number }>(
        `flowx/enrollments${toQuery({
          country: query.country,
          status: query.status,
          q: query.q,
          lead_id: query.lead_id,
        })}`
      ),
    staleTime: 15_000,
  });
}

export function useFlowxEnrollment(enrollmentId: string | null) {
  return useQuery({
    queryKey: ['flowx-enrollment', enrollmentId],
    queryFn: () => apiFetch<FlowxEnrollment>(`flowx/enrollments/${enrollmentId}`),
    enabled: Boolean(enrollmentId),
    staleTime: 5_000,
  });
}

export function useFlowxBoard(country?: string) {
  return useQuery({
    queryKey: ['flowx-board', country ?? ''],
    queryFn: () =>
      apiFetch<FlowxBoardResponse>(`flowx/board${toQuery({ country })}`),
    staleTime: 10_000,
  });
}

export function useMoveFlowxTask(enrollmentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      task_id: string;
      kanban_status: FlowxKanbanStatus;
      position_index: number;
      updated_at?: string | null;
    }) =>
      apiFetch<FlowxEnrollment>(`flowx/tasks/${payload.task_id}/move`, {
        method: 'PATCH',
        body: JSON.stringify({
          kanban_status: payload.kanban_status,
          position_index: payload.position_index,
          updated_at: payload.updated_at ?? undefined,
        }),
      }),
    onMutate: async payload => {
      if (!enrollmentId) return { previous: undefined };
      await qc.cancelQueries({ queryKey: ['flowx-enrollment', enrollmentId] });
      const previous = qc.getQueryData<FlowxEnrollment>(['flowx-enrollment', enrollmentId]);
      if (previous) {
        qc.setQueryData(['flowx-enrollment', enrollmentId], {
          ...previous,
          tracks: previous.tracks.map(track => ({
            ...track,
            tasks: track.tasks.map(task =>
              task.id === payload.task_id
                ? {
                    ...task,
                    kanban_status: payload.kanban_status,
                    position_index: payload.position_index,
                  }
                : task
            ),
          })),
        });
      }
      return { previous };
    },
    onError: (_e, _p, ctx) => {
      if (enrollmentId && ctx?.previous) {
        qc.setQueryData(['flowx-enrollment', enrollmentId], ctx.previous);
      }
    },
    onSuccess: data => {
      qc.setQueryData(['flowx-enrollment', data.id], data);
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
    },
  });
}

export function useUpdateFlowxTaskChecklist(enrollmentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      task_id: string;
      checked: boolean[];
      confirmed_complete: boolean;
      steps: string[];
      updated_at?: string | null;
    }) =>
      apiFetch<FlowxEnrollment>(`flowx/tasks/${payload.task_id}/checklist`, {
        method: 'PATCH',
        body: JSON.stringify({
          checked: payload.checked,
          confirmed_complete: payload.confirmed_complete,
          steps: payload.steps,
          updated_at: payload.updated_at ?? undefined,
        }),
      }),
    onMutate: async payload => {
      if (!enrollmentId) return { previous: undefined };
      await qc.cancelQueries({ queryKey: ['flowx-enrollment', enrollmentId] });
      const previous = qc.getQueryData<FlowxEnrollment>(['flowx-enrollment', enrollmentId]);
      if (previous) {
        qc.setQueryData(['flowx-enrollment', enrollmentId], {
          ...previous,
          tracks: previous.tracks.map(track => ({
            ...track,
            tasks: track.tasks.map(task =>
              task.id === payload.task_id
                ? {
                    ...task,
                    checklist_state: {
                      checked: payload.checked,
                      confirmed_complete: payload.confirmed_complete,
                      steps: payload.steps,
                      updated_at: new Date().toISOString(),
                    },
                  }
                : task
            ),
          })),
        });
      }
      return { previous };
    },
    onError: (_e, _p, ctx) => {
      if (enrollmentId && ctx?.previous) {
        qc.setQueryData(['flowx-enrollment', enrollmentId], ctx.previous);
      }
    },
    onSuccess: data => {
      qc.setQueryData(['flowx-enrollment', data.id], data);
    },
  });
}

/** Reorder child processes within a sub-process (track). */
export function useReorderFlowxTask(enrollmentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      task_id: string;
      position_index: number;
      updated_at?: string | null;
    }) =>
      apiFetch<FlowxEnrollment>(`flowx/tasks/${payload.task_id}/reorder`, {
        method: 'PATCH',
        body: JSON.stringify({
          position_index: payload.position_index,
          updated_at: payload.updated_at ?? undefined,
        }),
      }),
    onMutate: async payload => {
      if (!enrollmentId) return { previous: undefined };
      await qc.cancelQueries({ queryKey: ['flowx-enrollment', enrollmentId] });
      const previous = qc.getQueryData<FlowxEnrollment>(['flowx-enrollment', enrollmentId]);
      if (previous) {
        const parent = previous.tracks.find(t => t.tasks.some(task => task.id === payload.task_id));
        if (parent) {
          const moved = parent.tasks.find(t => t.id === payload.task_id);
          if (moved) {
            const siblings = parent.tasks
              .filter(t => t.id !== moved.id)
              .sort((a, b) => a.position_index - b.position_index);
            const pos = Math.max(0, Math.min(payload.position_index, siblings.length));
            siblings.splice(pos, 0, moved);
            const reindexed = siblings.map((t, idx) => ({ ...t, position_index: idx }));
            qc.setQueryData(['flowx-enrollment', enrollmentId], {
              ...previous,
              tracks: previous.tracks.map(track =>
                track.id === parent.id ? { ...track, tasks: reindexed } : track
              ),
            });
          }
        }
      }
      return { previous };
    },
    onError: (_e, _p, ctx) => {
      if (enrollmentId && ctx?.previous) {
        qc.setQueryData(['flowx-enrollment', enrollmentId], ctx.previous);
      }
    },
    onSuccess: data => {
      qc.setQueryData(['flowx-enrollment', data.id], data);
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
    },
  });
}

export function useUpdateFlowxStage(enrollmentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { current_stage_key: FlowxStageKey; updated_at?: string | null }) =>
      apiFetch<FlowxEnrollment>(`flowx/enrollments/${enrollmentId}/stage`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: data => {
      qc.setQueryData(['flowx-enrollment', data.id], data);
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
    },
  });
}

export function useMoveFlowxEnrollmentTrack(enrollmentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      track_id: string;
      position_index: number;
      updated_at?: string | null;
    }) =>
      apiFetch<FlowxEnrollment>(`flowx/enrollment-tracks/${payload.track_id}/move`, {
        method: 'PATCH',
        body: JSON.stringify({
          position_index: payload.position_index,
          updated_at: payload.updated_at ?? undefined,
        }),
      }),
    onMutate: async payload => {
      if (!enrollmentId) return { previous: undefined };
      await qc.cancelQueries({ queryKey: ['flowx-enrollment', enrollmentId] });
      const previous = qc.getQueryData<FlowxEnrollment>(['flowx-enrollment', enrollmentId]);
      if (previous) {
        const moved = previous.tracks.find(t => t.id === payload.track_id);
        if (moved) {
          const siblings = previous.tracks
            .filter(t => t.stage_key === moved.stage_key && t.id !== moved.id)
            .sort((a, b) => (a.position_index ?? 0) - (b.position_index ?? 0));
          const pos = Math.max(0, Math.min(payload.position_index, siblings.length));
          siblings.splice(pos, 0, moved);
          const reindexed = new Map(siblings.map((t, idx) => [t.id, idx]));
          qc.setQueryData(['flowx-enrollment', enrollmentId], {
            ...previous,
            tracks: previous.tracks.map(t =>
              reindexed.has(t.id) ? { ...t, position_index: reindexed.get(t.id)! } : t
            ),
          });
        }
      }
      return { previous };
    },
    onError: (_e, _p, ctx) => {
      if (enrollmentId && ctx?.previous) {
        qc.setQueryData(['flowx-enrollment', enrollmentId], ctx.previous);
      }
    },
    onSuccess: data => {
      qc.setQueryData(['flowx-enrollment', data.id], data);
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
    },
  });
}

export function useAddFlowxTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      track_id: string;
      title: string;
      description?: string;
      action_steps?: string[];
      parent_template_id?: string | null;
    }) =>
      apiFetch<FlowxCountryDetail>(`flowx/tracks/${payload.track_id}/templates`, {
        method: 'POST',
        body: JSON.stringify({
          title: payload.title,
          description: payload.description,
          action_steps: payload.action_steps ?? [],
          parent_template_id: payload.parent_template_id,
        }),
      }),
    onSuccess: data => {
      qc.setQueryData(['flowx-country', data.country_iso2], data);
      qc.invalidateQueries({ queryKey: ['flowx-countries'] });
    },
  });
}

export function useRenameFlowxTemplate() {
  const onSuccess = useCountryDetailMutation();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      template_id: string;
      title?: string;
      description?: string | null;
      action_steps?: string[];
    }) =>
      apiFetch<FlowxCountryDetail>(`flowx/templates/${payload.template_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          title: payload.title,
          description: payload.description,
          action_steps: payload.action_steps,
        }),
      }),
    onSuccess: data => {
      onSuccess(data);
      // Global rename — refresh every loaded country board.
      qc.invalidateQueries({ queryKey: ['flowx-country'] });
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
    },
  });
}

export function useRenameFlowxProcessLabel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { stage_key: FlowxStageKey; label: string }) =>
      apiFetch<{
        stage_key: FlowxStageKey;
        label: string;
        countries_updated: number;
        stages_updated: number;
      }>('flowx/process-labels', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
    onSuccess: (_data, vars) => {
      qc.setQueriesData<FlowxCountryDetail>({ queryKey: ['flowx-country'] }, old => {
        if (!old?.stages) return old;
        return {
          ...old,
          stages: old.stages.map(stage =>
            stage.stage_key === vars.stage_key ? { ...stage, label: vars.label } : stage
          ),
        };
      });
      qc.invalidateQueries({ queryKey: ['flowx-country'] });
      qc.invalidateQueries({ queryKey: ['flowx-countries'] });
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
    },
  });
}

function useCountryDetailMutation() {
  const qc = useQueryClient();
  return (data: FlowxCountryDetail) => {
    qc.setQueryData<FlowxCountryDetail>(['flowx-country', data.country_iso2], prev => ({
      ...data,
      institution_count: data.institution_count ?? prev?.institution_count,
      college_count: data.college_count ?? prev?.college_count,
      students_processed: data.students_processed ?? prev?.students_processed,
      students_in_process: data.students_in_process ?? prev?.students_in_process,
    }));
    qc.invalidateQueries({ queryKey: ['flowx-countries'] });
  };
}

export function useMoveFlowxTemplate() {
  const onSuccess = useCountryDetailMutation();
  return useMutation({
    mutationFn: (payload: {
      template_id: string;
      target_stage_id: string;
      position_index: number;
      track_name?: string;
    }) =>
      apiFetch<FlowxCountryDetail>(`flowx/templates/${payload.template_id}/move`, {
        method: 'PATCH',
        body: JSON.stringify({
          target_stage_id: payload.target_stage_id,
          position_index: payload.position_index,
          track_name: payload.track_name,
        }),
      }),
    onSuccess,
  });
}

export function useUnlinkFlowxTemplate() {
  const onSuccess = useCountryDetailMutation();
  return useMutation({
    mutationFn: (template_id: string) =>
      apiFetch<FlowxCountryDetail>(`flowx/templates/${template_id}/unlink`, { method: 'POST' }),
    onSuccess,
  });
}

export function useDeleteFlowxTemplate() {
  const onSuccess = useCountryDetailMutation();
  return useMutation({
    mutationFn: async (template_id: string) => {
      try {
        return await apiFetch<FlowxCountryDetail>(`flowx/templates/${template_id}`, {
          method: 'DELETE',
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        throw new Error(message);
      }
    },
    onSuccess,
  });
}

export function useFlowxTemplateUsage() {
  return useMutation({
    mutationFn: (template_id: string) =>
      apiFetch<{ template_id: string; student_task_count: number; in_use: boolean }>(
        `flowx/templates/${template_id}/usage`
      ),
  });
}

export function useRelinkFlowxTemplate() {
  const onSuccess = useCountryDetailMutation();
  return useMutation({
    mutationFn: (payload: {
      template_id: string;
      target_stage_id: string;
      track_name?: string;
      position_index?: number;
    }) =>
      apiFetch<FlowxCountryDetail>(`flowx/templates/${payload.template_id}/relink`, {
        method: 'POST',
        body: JSON.stringify({
          target_stage_id: payload.target_stage_id,
          track_name: payload.track_name,
          position_index: payload.position_index ?? 0,
        }),
      }),
    onSuccess,
  });
}

export function useOverrideFlowxTemplate() {
  const onSuccess = useCountryDetailMutation();
  return useMutation({
    mutationFn: (payload: {
      template_id: string;
      action: 'waive' | 'make_optional' | 'force_required' | 'clear';
      reason: string;
    }) =>
      apiFetch<FlowxCountryDetail>(`flowx/templates/${payload.template_id}/override`, {
        method: 'POST',
        body: JSON.stringify({ action: payload.action, reason: payload.reason }),
      }),
    onSuccess,
  });
}

export function useLinkFlowxSubprocesses() {
  const onSuccess = useCountryDetailMutation();
  return useMutation({
    mutationFn: (payload: {
      workflow_id: string;
      from_template_id: string;
      to_template_id: string;
      link_type?: 'depends_on' | 'related';
    }) =>
      apiFetch<FlowxCountryDetail>(`flowx/workflows/${payload.workflow_id}/links`, {
        method: 'POST',
        body: JSON.stringify({
          from_template_id: payload.from_template_id,
          to_template_id: payload.to_template_id,
          link_type: payload.link_type ?? 'depends_on',
        }),
      }),
    onSuccess,
  });
}

export function useUnlinkFlowxSubprocessLink() {
  const onSuccess = useCountryDetailMutation();
  return useMutation({
    mutationFn: (link_id: string) =>
      apiFetch<FlowxCountryDetail>(`flowx/links/${link_id}`, { method: 'DELETE' }),
    onSuccess,
  });
}

export function useFlowxOverride(enrollmentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      action_type: 'waive_step' | 'add_custom_task' | 'fast_forward' | 'override_sla';
      target_entity: string;
      reason: string;
      track_name?: string;
      stage_key?: FlowxStageKey;
      title?: string;
    }) =>
      apiFetch<FlowxEnrollment>(`flowx/enrollments/${enrollmentId}/overrides`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: data => {
      qc.setQueryData(['flowx-enrollment', data.id], data);
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
    },
  });
}

export function useFlowxJourneyTestSeed() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leadId: number) =>
      apiFetch<{
        lead_id: number;
        lead_name?: string | null;
        total: number;
        applications: unknown[];
      }>(`flowx/journey-test-data/seed${toQuery({ lead_id: leadId })}`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
      qc.invalidateQueries({ queryKey: ['flowx-countries'] });
      qc.invalidateQueries({ queryKey: ['flowx-destinations'] });
      qc.invalidateQueries({ queryKey: ['flowx-geography'] });
    },
  });
}

export function useFlowxJourneyTestReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (leadId: number) =>
      apiFetch<{
        lead_id: number;
        lead_name?: string | null;
        enrollments_deleted: number;
        academia: { institutions?: number };
      }>(`flowx/journey-test-data/reset${toQuery({ lead_id: leadId })}`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flowx-enrollments'] });
      qc.invalidateQueries({ queryKey: ['flowx-board'] });
      qc.invalidateQueries({ queryKey: ['flowx-countries'] });
      qc.invalidateQueries({ queryKey: ['flowx-destinations'] });
      qc.invalidateQueries({ queryKey: ['flowx-geography'] });
      qc.invalidateQueries({ queryKey: ['flowx-enrollment'] });
    },
  });
}
