import axios, { AxiosError } from 'axios';

/** Error shape normalised from the API's `{ error: { code, message, details } }` envelope. */
export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(message: string, status: number, code: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const ORG_KEY = 'edushield.activeOrg';

/** Platform administrators can scope requests to one institution; stored per browser tab only. */
export const orgScope = {
  get(): string | null {
    try {
      return sessionStorage.getItem(ORG_KEY);
    } catch {
      return null;
    }
  },
  set(id: string | null) {
    try {
      if (id) sessionStorage.setItem(ORG_KEY, id);
      else sessionStorage.removeItem(ORG_KEY);
    } catch {
      /* storage unavailable: scope falls back to the user's own institution */
    }
  },
};

export const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  timeout: 30_000,
  // Custom header required by the API on unsafe methods: a cross-site form cannot set it (CSRF defence).
  headers: { 'X-EduShield-Client': 'web' },
});

api.interceptors.request.use((config) => {
  const org = orgScope.get();
  if (org) config.headers.set('X-Organization-Id', org);
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ error?: { code?: string; message?: string; details?: unknown } }>) => {
    if (!err.response) {
      return Promise.reject(new ApiError('Unable to reach the EduShield API. Check that the backend is running.', 0, 'network_error'));
    }
    const { status, data } = err.response;
    if (status === 401 && !err.config?.url?.includes('/auth/')) {
      window.dispatchEvent(new CustomEvent('edushield:unauthorized'));
    }
    const body = data?.error;
    const message =
      body?.message ??
      (status === 403
        ? 'You do not have permission to perform this action.'
        : status === 404
          ? 'The requested record was not found.'
          : 'The request could not be completed.');
    return Promise.reject(new ApiError(message, status, body?.code ?? `http_${status}`, body?.details));
  },
);

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : 'Unexpected error';
}
