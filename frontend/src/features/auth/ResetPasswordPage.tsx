import { CheckCircle2, Lock } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { ApiError, api, errorMessage } from '@/lib/api';

function problemText(err: unknown) {
  if (err instanceof ApiError && Array.isArray(err.details)) {
    const messages = (err.details as { message?: string }[]).map((detail) => detail.message).filter(Boolean);
    if (messages.length > 0) return messages.join(' ');
  }
  return errorMessage(err);
}

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(token ? null : 'This password reset link is invalid or incomplete.');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || pending) return;
    if (password !== confirm) return setError('Passwords do not match.');
    setPending(true);
    setError(null);
    try {
      await api.post('/auth/password-reset/confirm', { token, password });
      setDone(true);
    } catch (err) {
      setError(problemText(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-50 px-4 py-10">
      <section className="w-full max-w-md rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 sm:p-8">
        {done ? (
          <div className="text-center">
            <CheckCircle2 className="mx-auto size-12 text-emerald-600" aria-hidden />
            <h1 className="mt-4 text-2xl font-semibold text-slate-900">Password changed</h1>
            <p className="mt-2 text-sm text-slate-600">Sign in with your new password. Other devices have been signed out.</p>
            <Link to="/login"><Button size="lg" className="mt-6 w-full">Sign in</Button></Link>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-semibold text-slate-900">Choose a new password</h1>
            <form className="mt-6 space-y-4" onSubmit={submit} noValidate>
              <Field label="New password" hint="At least 12 characters and three of: uppercase, lowercase, number, symbol.">
                {(id, d) => <Input id={id} aria-describedby={d} type="password" autoComplete="new-password" icon={<Lock className="size-4" />} value={password} onChange={(e) => setPassword(e.target.value)} disabled={!token} />}
              </Field>
              <Field label="Confirm new password">
                {(id) => <Input id={id} type="password" autoComplete="new-password" icon={<Lock className="size-4" />} value={confirm} onChange={(e) => setConfirm(e.target.value)} disabled={!token} />}
              </Field>
              {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-100">{error}</p>}
              <Button type="submit" size="lg" className="w-full" loading={pending} disabled={!token}>Change password</Button>
            </form>
            <Link to="/forgot-password" className="mt-5 inline-block text-sm font-medium text-brand-blue hover:underline">Request a new link</Link>
          </>
        )}
      </section>
    </main>
  );
}
