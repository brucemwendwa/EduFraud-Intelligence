import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '@/lib/api';
import { renderWithProviders } from '@/test/render';
import ForgotPasswordPage from './ForgotPasswordPage';
import ResetPasswordPage from './ResetPasswordPage';

describe('password recovery pages', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('confirms the request without saying whether the account exists', async () => {
    const user = userEvent.setup();
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: {} });
    renderWithProviders(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText('Email address'), 'student@example.edu');
    await user.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByRole('status')).toHaveTextContent('If that address has an account');
    expect(post).toHaveBeenCalledWith('/auth/password-reset/request', { email: 'student@example.edu' });
  });

  it('refuses mismatched passwords before calling the API', async () => {
    const user = userEvent.setup();
    const post = vi.spyOn(api, 'post');
    renderWithProviders(<ResetPasswordPage />, { route: '/reset-password?token=abc' });
    await user.type(screen.getByLabelText('New password'), 'Correct-Horse-2026!');
    await user.type(screen.getByLabelText('Confirm new password'), 'Different-2026!');
    await user.click(screen.getByRole('button', { name: 'Change password' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match.');
    expect(post).not.toHaveBeenCalled();
  });

  it('shows the password policy problems from the API', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'post').mockRejectedValue(new ApiError('Password does not meet the policy.', 422, 'validation_failed', [{ field: 'password', message: 'Use at least 12 characters.' }]));
    renderWithProviders(<ResetPasswordPage />, { route: '/reset-password?token=abc' });
    await user.type(screen.getByLabelText('New password'), 'short');
    await user.type(screen.getByLabelText('Confirm new password'), 'short');
    await user.click(screen.getByRole('button', { name: 'Change password' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Use at least 12 characters.'));
  });

  it('explains a missing token and disables the form', () => {
    renderWithProviders(<ResetPasswordPage />, { route: '/reset-password' });
    expect(screen.getByRole('alert')).toHaveTextContent('invalid or incomplete');
    expect(screen.getByRole('button', { name: 'Change password' })).toBeDisabled();
  });
});
