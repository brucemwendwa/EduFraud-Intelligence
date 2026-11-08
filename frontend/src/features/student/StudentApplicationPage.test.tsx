import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';

const application = {
  id: 'app-1', reference: 'FA-2026-1', award_year: '2026-27', status: 'draft', submitted_at: null,
  dependency_status: null, enrollment_intensity: null, program: null, requested_amount: null, student_aid_index: null,
  risk_level: null, is_editable: true, outstanding_requirements: [], history: [],
};

vi.mock('@/lib/auth', () => ({ useAuth: () => ({ user: { role: { key: 'student' } } }) }));
vi.mock('./studentApplications', () => ({
  useStudentApplication: () => ({ data: application, isLoading: false, error: null, refetch: vi.fn() }),
  useStudentApplicationActions: () => ({
    create: { isPending: false, mutateAsync: vi.fn() }, save: { isPending: false, mutateAsync: vi.fn() },
    submit: { isPending: false, mutateAsync: vi.fn() }, withdraw: { isPending: false, mutateAsync: vi.fn() },
  }),
}));
vi.mock('@/features/documents/StudentDocumentPanel', () => ({
  StudentDocumentPanel: ({ applicationId, isEditable }: { applicationId: string; isEditable: boolean }) =>
    <div data-testid="document-panel">{applicationId}:{String(isEditable)}</div>,
}));

import StudentApplicationPage from './StudentApplicationPage';

describe('StudentApplicationPage', () => {
  it('places the student document panel in the loaded application workflow', () => {
    renderWithProviders(<StudentApplicationPage />, { route: '/student/applications/app-1' });
    expect(screen.getByTestId('document-panel')).toHaveTextContent('app-1:true');
  });
});
