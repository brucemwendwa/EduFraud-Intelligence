import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';

const can = vi.fn((permission: string) => permission === 'applications:review');
const panel = vi.fn(({ applicationId }: { applicationId: string }) => <div data-testid="evidence-panel">Evidence for {applicationId}</div>);
vi.mock('./api', () => ({ useApplication: () => ({ isLoading: false, error: null, refetch: vi.fn(), data: {
  id: 'application-42', reference: 'FA-42', organization: { name: 'Northbridge' }, award_year: '2026-27', submitted_at: '2026-01-01T00:00:00Z', status: 'received', review_status: 'unreviewed', verification_status: 'not_required', scenario_key: null,
  alerts: [], related: [], disbursements: [], enrollments: [], verifications: [], program: 'Science', requested_amount: '1000', student_aid_index: 0, dependency_status: 'dependent', enrollment_intensity: 'full_time', submission_channel: 'web', device_handle: null,
  student_detail: { identity_tokens: [] },
} }) }));
vi.mock('@/lib/auth', () => ({ useAuth: () => ({ can }) }));
vi.mock('@/features/documents/StaffDocumentPanel', () => ({ StaffDocumentPanel: (props: { applicationId: string }) => panel(props) }));
vi.mock('./ReviewDialog', () => ({ ReviewDialog: () => <div data-testid="review-dialog" /> }));
vi.mock('@/features/verification/VerificationWizard', () => ({ VerificationWizard: () => null }));
vi.mock('./RiskPanel', () => ({ RiskPanel: () => <div>Risk panel</div> }));
vi.mock('./StudentIdentityCard', () => ({ StudentIdentityCard: () => <div>Student identity</div> }));
vi.mock('@/features/cases/OpenCaseButton', () => ({ OpenCaseButton: () => null }));
import ApplicationDetailPage from './ApplicationDetailPage';

describe('ApplicationDetailPage evidence integration', () => {
  it('switches to Evidence with the displayed application id and preserves review controls', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ApplicationDetailPage />, { route: '/app/applications/application-42' });
    expect(screen.getByRole('button', { name: 'Record review' })).toBeInTheDocument();
    const evidence = screen.getByRole('tab', { name: 'Evidence' });
    await user.click(evidence);
    expect(screen.getByTestId('evidence-panel')).toHaveTextContent('application-42');
    expect(panel).toHaveBeenCalledWith(expect.objectContaining({ applicationId: 'application-42' }));
    await user.click(screen.getByRole('tab', { name: /Related records/ }));
    expect(screen.getByText('No shared attributes')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Record review' })).toBeInTheDocument();
  });
});
