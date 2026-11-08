import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';

const data = {
  profile: { full_name: 'Sam Rivera', email: 's@x.edu', student_ref: 'STU-1', institution: 'Northbridge' },
  counts: { total: 7, draft: 2, submitted: 1, under_review: 1, additional_information: 1, approved: 1, rejected: 1, withdrawn: 0 },
  information_requests: [{ application_id: 'a1', reference: 'FA-1', program: 'Biology', message: 'Upload your enrollment letter.', requested_at: '2026-11-01T00:00:00Z' }],
  recent_activity: [{ kind: 'status_change', application_id: 'a1', reference: 'FA-1', title: 'Additional information requested', detail: null, occurred_at: '2026-11-01T00:00:00Z' }],
  applications: [{ id: 'a2', reference: 'FA-2', status: 'draft', award_year: null, program: null, requested_amount: null, submitted_at: null, is_editable: true }],
};
const hook = vi.fn();
vi.mock('./studentApplications', () => ({ useStudentDashboard: () => hook() }));
import StudentDashboardPage from './StudentDashboardPage';

describe('StudentDashboardPage', () => {
  it('renders server figures, with each tile linking to its filtered list', () => {
    hook.mockReturnValue({ data, isLoading: false, error: null, refetch: vi.fn() });
    renderWithProviders(<StudentDashboardPage />);
    expect(screen.getByText('Welcome, Sam Rivera')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /All applications\s*7/ })).toHaveAttribute('href', '/student/applications');
    expect(screen.getByRole('link', { name: /Drafts\s*2/ })).toHaveAttribute('href', '/student/applications?status=draft');
    expect(screen.getByRole('link', { name: /Action needed\s*1/ })).toHaveAttribute('href', '/student/applications?status=additional_information');
  });

  it('puts outstanding requests first and offers the right next action', () => {
    hook.mockReturnValue({ data, isLoading: false, error: null, refetch: vi.fn() });
    renderWithProviders(<StudentDashboardPage />);
    expect(screen.getByText('Upload your enrollment letter.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Respond/ })).toHaveAttribute('href', '/student/applications/a1');
    expect(screen.getByRole('link', { name: /Untitled application/ })).toHaveTextContent('Continue draft');
  });

  it('reports a load failure instead of showing empty figures', () => {
    hook.mockReturnValue({ data: undefined, isLoading: false, error: new Error('Unavailable'), refetch: vi.fn() });
    renderWithProviders(<StudentDashboardPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load your aid information');
  });
});
