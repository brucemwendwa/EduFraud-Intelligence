import { screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApplicationRow, Page } from '@/api/types';
import { renderWithProviders } from '@/test/render';
import ApplicationsPage from './ApplicationsPage';

const get = vi.fn();
vi.mock('@/lib/api', async (orig) => ({ ...(await orig<typeof import('@/lib/api')>()), api: { get: (...a: unknown[]) => get(...a) } }));
vi.mock('@/lib/auth', () => ({
  useAuth: () => ({ user: { is_platform_admin: false }, activeOrgId: null, can: () => true }),
}));

const row: ApplicationRow = {
  id: 'a1',
  reference: 'FA-2026-104871',
  organization: { id: 'o1', name: 'Northbridge State University', slug: 'northbridge' },
  student: { id: 's1', student_ref: 'STU-00042', masked_name: 'M*** R***' },
  submitted_at: '2026-09-01T10:00:00Z',
  award_year: '2026-27',
  status: 'received',
  requested_amount: '12500.00',
  verification_status: 'failed',
  review_status: 'unreviewed',
  risk_score: 86.4,
  risk_level: 'critical',
  last_assessed_at: '2026-10-30T10:00:00Z',
  scenario_key: 'coordinated_network',
  open_alerts: 2,
};

const page = (items: ApplicationRow[]): Page<ApplicationRow> => ({ items, total: items.length, page: 1, page_size: 20 });

describe('ApplicationsPage', () => {
  beforeEach(() => get.mockReset());

  it('renders rows with masked identity, explainable risk and scenario tag', async () => {
    get.mockResolvedValue({ data: page([row]) });
    renderWithProviders(<ApplicationsPage />);
    expect(await screen.findByText('FA-2026-104871')).toBeInTheDocument();
    const table = within(screen.getByRole('table'));
    expect(table.getByText('M*** R***')).toBeInTheDocument();
    expect(table.getByText('Critical')).toBeInTheDocument();
    expect(table.getByText('Coordinated network')).toBeInTheDocument();
    expect(table.getByTitle('2 open alert(s)')).toBeInTheDocument();
  });

  it('sends URL filters to the API', async () => {
    get.mockResolvedValue({ data: page([row]) });
    renderWithProviders(<ApplicationsPage />, { route: '/app/applications?risk_level=critical&scenario=any' });
    await screen.findByText('FA-2026-104871');
    expect(get).toHaveBeenCalledWith('/applications', {
      params: expect.objectContaining({ risk_level: 'critical', scenario: 'any', page_size: '20' }),
    });
  });

  it('shows an empty state with a reset action when filters match nothing', async () => {
    get.mockResolvedValue({ data: page([]) });
    renderWithProviders(<ApplicationsPage />, { route: '/app/applications?risk_level=low' });
    expect(await screen.findByText('No applications match these filters')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Clear filters' }).length).toBeGreaterThan(0);
  });
});
