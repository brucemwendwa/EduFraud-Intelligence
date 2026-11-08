import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';

const mutate = vi.fn();
vi.mock('./api', () => ({ useReviewApplication: () => ({ mutate, isPending: false }) }));
import { ReviewDialog } from './ReviewDialog';

const ALL = ['additional_information_required', 'approved', 'in_review', 'on_hold', 'rejected'];
const renderDialog = (allowed = ALL) =>
  renderWithProviders(<ReviewDialog applicationId="a1" reference="FA-1" currentStatus="submitted" allowedStatusChanges={allowed} open onOpenChange={vi.fn()} />);

describe('ReviewDialog', () => {
  beforeEach(() => mutate.mockReset());

  it('offers only the transitions the API allows', () => {
    renderDialog(['in_review']);
    const options = Array.from(screen.getByLabelText('Application decision').querySelectorAll('option')).map((o) => o.value);
    expect(options).toEqual(['', 'in_review']);
  });

  it('requires a student-facing explanation to reject', async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.selectOptions(screen.getByLabelText('Application decision'), 'rejected');
    await user.type(screen.getByLabelText('Internal review note'), 'Enrollment mismatch confirmed.');
    const save = screen.getByRole('button', { name: 'Save decision' });
    expect(save).toBeDisabled();
    expect(screen.getByText(/final decision/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Message to the student'), 'Enrollment could not be verified.');
    expect(save).toBeEnabled();
    await user.click(save);
    expect(mutate.mock.calls[0]![0]).toEqual({
      review_status: 'in_review',
      application_status: 'rejected',
      note: 'Enrollment mismatch confirmed.',
      student_message: 'Enrollment could not be verified.',
    });
  });

  it('does not send a student message for an internal-only review', async () => {
    const user = userEvent.setup();
    renderDialog();
    expect(screen.queryByLabelText(/Message to the student/)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Internal review note'), 'Checked the file.');
    await user.click(screen.getByRole('button', { name: 'Save decision' }));
    expect(mutate.mock.calls[0]![0]).toMatchObject({ application_status: null, student_message: null });
  });
});
