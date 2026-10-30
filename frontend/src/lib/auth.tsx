import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router';
import type { Me } from '@/api/types';
import { Spinner } from '@/components/ui/Spinner';
import { api, ApiError, orgScope } from './api';
import type { Permission } from './permissions';

interface AuthContextValue {
  user: Me | null;
  loading: boolean;
  can: (p: Permission) => boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  activeOrgId: string | null;
  setActiveOrgId: (id: string | null) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
export const meKey = ['auth', 'me'] as const;

/** Drops every cached query except the session itself (observers of `meKey` must stay attached). */
const dropDataQueries = (qc: ReturnType<typeof useQueryClient>) =>
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'auth' });

async function fetchMe(): Promise<Me | null> {
  try {
    return (await api.get<Me>('/auth/me')).data;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: meKey, queryFn: fetchMe, retry: false, staleTime: 5 * 60_000 });
  const [activeOrgId, setActiveOrg] = useState<string | null>(() => orgScope.get());

  useEffect(() => {
    const onUnauthorized = () => qc.setQueryData(meKey, null);
    window.addEventListener('edushield:unauthorized', onUnauthorized);
    return () => window.removeEventListener('edushield:unauthorized', onUnauthorized);
  }, [qc]);

  const login = useCallback(
    async (email: string, password: string) => {
      const me = (await api.post<Me>('/auth/login', { email, password })).data;
      orgScope.set(null);
      setActiveOrg(null);
      dropDataQueries(qc);
      qc.setQueryData(meKey, me);
      return me;
    },
    [qc],
  );

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } finally {
      orgScope.set(null);
      setActiveOrg(null);
      dropDataQueries(qc);
      qc.setQueryData(meKey, null);
    }
  }, [qc]);

  const setActiveOrgId = useCallback(
    (id: string | null) => {
      orgScope.set(id);
      setActiveOrg(id);
      // Every tenant-scoped query must refetch under the new institution scope.
      dropDataQueries(qc);
    },
    [qc],
  );

  const value = useMemo<AuthContextValue>(() => {
    const perms = new Set(data?.permissions ?? []);
    return {
      user: data ?? null,
      loading: isLoading,
      can: (p) => perms.has(p),
      login,
      logout,
      activeOrgId,
      setActiveOrgId,
    };
  }, [data, isLoading, login, logout, activeOrgId, setActiveOrgId]);

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const ctx = use(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

/** Route guard: renders child routes only for an authenticated session. */
export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-navy-700">
        <Spinner className="size-6" label="Checking session" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <Outlet />;
}
