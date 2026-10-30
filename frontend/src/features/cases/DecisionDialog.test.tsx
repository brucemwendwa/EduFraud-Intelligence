import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CaseDetail } from '@/api/types';
import { renderWithProviders } from '@/test/render';
import { allowedDecisions, DecisionDialog } from './DecisionDialog';

const post = vi.fn();
vi.mock('@/lib/api', async (orig) => ({ ...(await orig<typeof import('@/lib/api')>()), api: { post: (...a: unknown[]) => post(...a) } }));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ user: { full_name: 'Marcus Bell' }, can: () => true }) }));

const baseCase = (overrides: Partial<CaseDetail> = {}): CaseDetail => ({
  id: 'c1', reference: 'CASE-00042', title: 'Unusual disbursement activity', application_id: 'a1', application_ref: 'FA-1',
  fraud_category: 'disbursement', priority: 'high', status: 'under_review', finding: 'suspicious_activity',
  risk_score_at_open: 68, assigned_to: null, created_by: null, due_at: null, overdue: false,
  created_at: '2026-10-30T10:00:00Z', updated_at: '2026-10-30T10:00:00Z', resolution: null, resolution_summary: null,
  resolved_at: null, closed_at: null, application: null, alerts: [], evidence: [], notes: [], decisions: [], timeline: [],
  ...overrides,
});

const JUSTIFICATION = 'Student confirmed the bank change through the phone number on file.';

describe('DecisionDialog', () => {
  beforeEach(() => post.mockReset());

  it('offers only decisions valid for the status', () => {
    expect(allowedDecisions('new')).toEqual(['escalate', 'resolve']);
    expect(allowedDecisions('escalated')).toEqual(['resolve']);
    expect(allowedDecisions('resolved')).toEqual(['reopen', 'close']);
    expect(allowedDecisions('closed')).toEqual([]);
  });

  it('blocks a confirmed-fraud finding when no evidence is attached', async () => {
    renderWithProviders(<DecisionDialog c={baseCase()} open onOpenChange={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: /^Resolve/ }));
    expect(screen.getByRole('button', { name: /Confirmed fraud/ })).toBeDisabled();
  });

  it('requires an outcome, a justification and an acknowledgement before recording', async () => {
    post.mockResolvedValue({ data: baseCase({ status: 'resolved', finding: 'not_substantiated' }) });
    renderWithProviders(<DecisionDialog c={baseCase()} open onOpenChange={() => {}} />);
    const record = screen.getByRole('button', { name: 'Record decision' });

    await userEvent.click(screen.getByRole('button', { name: /^Resolve/ }));
    await userEvent.click(screen.getByRole('button', { name: /No fraud found/ }));
    await userEvent.type(screen.getByLabelText('Justification'), 'too short');
    expect(record).toBeDisabled();
    await userEvent.clear(screen.getByLabelText('Justification'));
    await userEvent.type(screen.getByLabelText('Justification'), JUSTIFICATION);
    expect(record).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox'));
    expect(record).toBeEnabled();
    expect(screen.getByText('Not substantiated')).toBeInTheDocument();

    await userEvent.click(record);
    expect(post).toHaveBeenCalledWith('/cases/c1/decision', {
      decision: 'resolve', outcome: 'no_fraud_found', justification: JUSTIFICATION, acknowledged: true,
    });
  });

  it('demands a fuller justification for a confirmed finding', async () => {
    const withEvidence = baseCase({
      evidence: [{ id: 'e1', evidence_type: 'alert', ref_id: 'x', ref_label: 'ALT-1', title: 'Alert', summary: 's', data: {}, created_at: '2026-10-30T10:00:00Z', added_by: null }],
    });
    renderWithProviders(<DecisionDialog c={withEvidence} open onOpenChange={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: /^Resolve/ }));
    await userEvent.click(screen.getByRole('button', { name: /Confirmed fraud/ }));
    await userEvent.type(screen.getByLabelText('Justification'), 'Twenty-five characters ok');
    await userEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
    expect(screen.getByText(/\/50/)).toBeInTheDocument();
  });
});
