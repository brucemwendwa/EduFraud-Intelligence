import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ApplicationDetail } from '@/api/types';
import { renderWithProviders } from '@/test/render';

vi.mock('@/lib/auth', () => ({ useAuth: () => ({ can: () => false }) }));
vi.mock('./api', () => ({ useAssessApplication: () => ({ mutate: vi.fn(), isPending: false }) }));
import { RiskPanel } from './RiskPanel';

const assessment = {
  id: 'r1', score: 42, level: 'medium', method: 'hybrid', rules_version: 'rules-1', model_version: 'model-1', explanation: 'Two signals.',
  recommended_action: 'Review manually.', triggered_by: 'student_submission', created_at: '2026-11-01T00:00:00Z', signals: [],
  provenance: { engine: 'hybrid', rules_version: 'rules-1', model_version: 'model-1', graph_version: 'graph-1', model_applied: true, population_size: 481, real_records_in_population: 0 },
  input_fingerprint: 'a'.repeat(64), score_reproducible: true, limitations: ['This score prioritises human review. It is not a finding of fraud and cannot approve or deny aid.'],
};
const app = (overrides = {}) => ({ id: 'a1', assessment: { ...assessment, ...overrides }, assessment_history: [] }) as unknown as ApplicationDetail;

describe('RiskPanel', () => {
  it('shows where the result came from and what it cannot tell you', () => {
    renderWithProviders(<RiskPanel app={app()} />);
    expect(screen.getByText('graph-1')).toBeInTheDocument();
    expect(screen.getByText('481')).toBeInTheDocument();
    expect(screen.getByText('Recomputes from these signals')).toBeInTheDocument();
    expect(screen.getByText(/It is not a finding of fraud/)).toBeInTheDocument();
  });

  it('flags a score that no longer matches its signals', () => {
    renderWithProviders(<RiskPanel app={app({ score_reproducible: false })} />);
    expect(screen.getByText('Could not be recomputed')).toBeInTheDocument();
  });
});
