import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';

const can = vi.fn(() => true);
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ can, user: { organization: { name: 'Northbridge' } } }) }));
const hook = vi.fn();
vi.mock('./api', () => ({ useOperationsOverview: () => hook() }));
import OperationsPage from './OperationsPage';

const data = {
  generated_at: '2026-11-01T00:00:00Z', scope: 'institution', environment: 'development', overall_health: 'ok',
  health: [
    { key: 'database', name: 'Database', status: 'ok', detail: 'Responding to queries.' },
    { key: 'scanner', name: 'Malware scanner', status: 'not_configured', detail: 'No scanner configured.' },
    { key: 'identity', name: 'Identity verification', status: 'simulated', detail: 'Deterministic simulation.' },
  ],
  applications: { submitted_24h: 3, submitted_7d: 9, decisions_24h: 1, decisions_7d: 4, awaiting_review: 12, additional_information_required: 1, open_total: 20, oldest_waiting_since: '2026-10-01T00:00:00Z' },
  risk: { assessments_24h: 5, assessments_7d: 11, open_elevated: 2, open_unassessed: 1, last_run_status: 'completed', last_run_finished_at: null, failed_runs_7d: 0 },
  documents: { pending_scan: 4, scanning: 0, available: 2, rejected: 1, failed: 1, superseded: 0, awaiting_staff_review: 2 },
  jobs: { scan_queued: 0, scan_running: 0, scan_retrying: 4, scan_failed: 1, cleanup_failed: 0, stalled: 0, recent_failures: [{ kind: 'document_scan', status: 'failed', error_code: 'unavailable', attempts: 3, occurred_at: '2026-11-01T00:00:00Z' }] },
  recent_audit: [{ sequence: 9, occurred_at: '2026-11-01T00:00:00Z', category: 'application', action: 'application.submit', outcome: 'success', actor_role: 'student' }],
};

describe('OperationsPage', () => {
  it('keeps unconfigured and simulated services distinct from healthy ones', () => {
    hook.mockReturnValue({ data, isLoading: false, error: null, refetch: vi.fn() });
    renderWithProviders(<OperationsPage />);
    expect(screen.getByText('Not configured')).toBeInTheDocument();
    expect(screen.getByText('Simulated')).toBeInTheDocument();
    expect(screen.getByText('2 services not live')).toBeInTheDocument();
  });

  it('shows processing counts, job failures and audit actions from the API', () => {
    hook.mockReturnValue({ data, isLoading: false, error: null, refetch: vi.fn() });
    renderWithProviders(<OperationsPage />);
    expect(screen.getByRole('link', { name: /Awaiting review\s*12/ })).toBeInTheDocument();
    expect(screen.getByText('unavailable')).toBeInTheDocument();
    expect(screen.getByText('application.submit')).toBeInTheDocument();
  });

  it('hides the audit panel from viewers without audit access', () => {
    can.mockReturnValue(false);
    hook.mockReturnValue({ data, isLoading: false, error: null, refetch: vi.fn() });
    renderWithProviders(<OperationsPage />);
    expect(screen.queryByText('Recent audit events')).not.toBeInTheDocument();
    can.mockReturnValue(true);
  });
});
