import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

/**
 * Filter/sort/page state kept in the URL so views are shareable and survive reloads.
 * Changing any filter resets pagination to page 1.
 */
export function useSearchState<T extends Record<string, string>>(defaults: T) {
  const [params, setParams] = useSearchParams();

  const state = useMemo(() => {
    const out = { ...defaults } as T;
    for (const key of Object.keys(defaults) as (keyof T)[]) {
      const v = params.get(key as string);
      if (v != null) out[key] = v as T[keyof T];
    }
    return out;
  }, [params, defaults]);

  const update = useCallback(
    (patch: Partial<T>) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(patch)) {
            if (v === undefined || v === '' || v === defaults[k]) next.delete(k);
            else next.set(k, v as string);
          }
          if (!('page' in patch)) next.delete('page');
          return next;
        },
        { replace: true },
      );
    },
    [setParams, defaults],
  );

  const reset = useCallback(() => setParams(new URLSearchParams(), { replace: true }), [setParams]);
  return [state, update, reset] as const;
}

/** Converts filter state into API query params, dropping empty values. */
export function toParams(state: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(state).filter(([, v]) => v !== '' && v != null));
}
