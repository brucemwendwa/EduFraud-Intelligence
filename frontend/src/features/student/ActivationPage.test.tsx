import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import ActivationPage from './ActivationPage';
import { renderWithProviders } from '@/test/render';

describe('ActivationPage', () => {
  it('rejects mismatched passwords before requesting activation', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ActivationPage />, { route: '/activate?token=abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG' });
    await user.type(screen.getByLabelText('Create password'), 'Strong!Activation2026');
    await user.type(screen.getByLabelText('Confirm password'), 'Different!Activation2026');
    await user.click(screen.getByRole('button', { name: 'Activate account' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match.');
  });

  it('shows an invalid-link state without a token', () => {
    renderWithProviders(<ActivationPage />, { route: '/activate' });
    expect(screen.getByRole('alert')).toHaveTextContent('invalid or incomplete');
    expect(screen.getByRole('button', { name: 'Activate account' })).toBeDisabled();
  });
});
