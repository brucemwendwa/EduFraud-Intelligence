import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from './Dialog';

describe('ConfirmDialog', () => {
  it('requires a justification before confirming when reasonLabel is set', async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog open onOpenChange={() => {}} title="Reveal student name" reasonLabel="Reason for access" onConfirm={onConfirm} />,
    );
    const confirm = screen.getByRole('button', { name: 'Confirm' });
    expect(confirm).toBeDisabled();

    await userEvent.type(screen.getByLabelText('Reason for access'), 'Case CASE-2026-0042 review');
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith('Case CASE-2026-0042 review');
  });

  it('confirms immediately when no reason is required', async () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog open onOpenChange={() => {}} title="Acknowledge alert" onConfirm={onConfirm} />);
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalledWith('');
  });
});
