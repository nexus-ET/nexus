/** Real selectable values count (>3 triggers multiselect). Excludes empty placeholder options. */
export function shouldUseMultiSelect(options: { value: string }[]): boolean {
  return options.filter(option => option.value !== '').length > 3;
}

/** Read repeated or comma-separated query values from URLSearchParams. */
export function readMultiParam(params: URLSearchParams, key: string): string[] {
  const repeated = params.getAll(key).map(value => value.trim()).filter(Boolean);
  if (repeated.length === 0) return [];
  if (repeated.length === 1 && repeated[0].includes(',')) {
    return repeated[0]
      .split(',')
      .map(value => value.trim())
      .filter(Boolean);
  }
  return repeated;
}

export function readSingleParam(params: URLSearchParams, key: string): string {
  const values = readMultiParam(params, key);
  return values[0] || '';
}

export function appendMultiParam(params: URLSearchParams, key: string, values: string[]): void {
  params.delete(key);
  for (const value of values) {
    if (value) params.append(key, value);
  }
}

export type FilterParamValue = string | string[] | null;

/** Apply single or repeated query param updates. null clears the key. */
export function applyFilterParamUpdates(
  params: URLSearchParams,
  updates: Record<string, FilterParamValue>
): void {
  for (const [key, value] of Object.entries(updates)) {
    params.delete(key);
    if (value == null) continue;
    if (Array.isArray(value)) {
      appendMultiParam(params, key, value);
      continue;
    }
    if (value !== '') params.set(key, value);
  }
}
