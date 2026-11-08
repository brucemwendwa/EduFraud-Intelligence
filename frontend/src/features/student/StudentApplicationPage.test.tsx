import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router';
import type { StudentApplication } from '@/api/types';
import { ApiError } from '@/lib/api';
import { renderWithProviders } from '@/test/render';

const draft: StudentApplication = {
  id: 'app-1', reference: 'FA-2026-1', award_year: '2026-2027', status: 'draft', submitted_at: null,
  dependency_status: null, enrollment_intensity: null, program: 'Biology', requested_amount: null, student_aid_index: null,
  is_editable: true, is_withdrawable: true, outstanding_requirements: [], status_message: null, history: [],
};
const state: { application: StudentApplication } = { application: draft };
const save = vi.fn();
const submit = vi.fn();
const withdraw = vi.fn();

vi.mock('./studentApplications', () => ({
  useStudentApplication: () => ({ data: state.application, isLoading: false, error: null, refetch: vi.fn() }),
  useStudentApplicationActions: () => ({
    create: { isPending: false, mutateAsync: vi.fn() },
    save: { isPending: false, mutateAsync: save },
    submit: { isPending: false, mutateAsync: submit },
    withdraw: { isPending: false, mutateAsync: withdraw },
  }),
}));
vi.mock('@/features/documents/StudentDocumentPanel', () => ({
  StudentDocumentPanel: ({ applicationId, isEditable }: { applicationId: string; isEditable: boolean }) =>
    <div data-testid="document-panel">{applicationId}:{String(isEditable)}</div>,
}));

import StudentApplicationPage from './StudentApplicationPage';

const renderPage = () =>
  renderWithProviders(
    <Routes><Route path="/student/applications/:id" element={<StudentApplicationPage />} /></Routes>,
    { route: '/student/applications/app-1' },
  );

describe('StudentApplicationPage', () => {
  beforeEach(() => {
    state.application = draft;
    save.mockReset().mockResolvedValue(draft);
    submit.mockReset().mockResolvedValue(draft);
    withdraw.mockReset().mockResolvedValue(draft);
  });

  it('places the student document panel in the loaded application workflow', () => {
    renderPage();
    expect(screen.getByTestId('document-panel')).toHaveTextContent('app-1:true');
  });

  it('saves what the student typed before submitting it', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.clear(screen.getByLabelText('Program'));
    await user.type(screen.getByLabelText('Program'), 'Data Science');
    await user.click(screen.getByRole('button', { name: 'Submit application' }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith({ id: 'app-1', responseNote: '' }));
    expect(save.mock.calls[0]![0]).toMatchObject({ id: 'app-1', body: { program: 'Data Science' } });
    expect(save.mock.invocationCallOrder[0]).toBeLessThan(submit.mock.invocationCallOrder[0]!);
  });

  it('names the missing fields when submission is refused', async () => {
    const user = userEvent.setup();
    submit.mockRejectedValue(new ApiError('Complete the required information before submitting.', 422, 'validation_failed', [{ field: 'program' }, { field: 'student aid index' }]));
    renderPage();
    await user.click(screen.getByRole('button', { name: 'Submit application' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Check: program, student aid index.');
  });

  it('shows the office request and lets the student respond with a note', async () => {
    const user = userEvent.setup();
    state.application = { ...draft, status: 'additional_information_required', status_message: { status: 'additional_information_required', message: 'Please upload your enrollment letter.', created_at: '2026-11-01T00:00:00Z' } };
    renderPage();
    expect(screen.getByText('Please upload your enrollment letter.')).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Note to your financial aid office/), 'Uploaded today.');
    await user.click(screen.getByRole('button', { name: 'Resubmit application' }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith({ id: 'app-1', responseNote: 'Uploaded today.' }));
  });

  it('asks for confirmation before withdrawing', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('button', { name: 'Withdraw application' }));
    expect(withdraw).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Withdraw application' }));
    await waitFor(() => expect(withdraw).toHaveBeenCalledWith('app-1'));
  });

  it('is read-only after a final decision and never shows internal labels', () => {
    state.application = {
      ...draft, status: 'rejected', is_editable: false, is_withdrawable: false,
      status_message: { status: 'rejected', message: 'Enrollment could not be verified.', created_at: '2026-11-01T00:00:00Z' },
      history: [{ from_status: 'submitted', to_status: 'rejected', actor_role: 'financial_aid_office', student_message: 'Enrollment could not be verified.', created_at: '2026-11-01T00:00:00Z' }],
    };
    renderPage();
    expect(screen.getByLabelText('Program')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Submit application' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Withdraw application' })).not.toBeInTheDocument();
    expect(screen.getByText(/Financial aid office/)).toBeInTheDocument();
  });
});
