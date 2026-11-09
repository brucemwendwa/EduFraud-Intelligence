import { Mail } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { Logo } from '@/components/layout/Logo';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { api, errorMessage } from '@/lib/api';

/** The confirmation is the same whether or not the address has an account. */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!email.trim()) return setError('Enter your email address.');
    setPending(true);
    setError(null);
    try {
      await api.post('/auth/password-reset/request', { email: email.trim() });
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-50 px-4 py-10">
      <section className="w-full max-w-md rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 sm:p-8">
        <Link to="/" aria-label="EduShield AI home"><Logo /></Link>
        <h1 className="mt-6 text-2xl font-semibold text-slate-900">Reset your password</h1>
        {sent ? (
          <p role="status" className="mt-3 text-sm text-slate-600">
            If that address has an account, a reset link is on its way. The link expires soon and can be used once.
          </p>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={submit} noValidate>
            <Field label="Email address" error={error}>
              {(id, d) => <Input id={id} aria-describedby={d} type="email" autoComplete="username" icon={<Mail className="size-4" />} value={email} onChange={(e) => setEmail(e.target.value)} />}
            </Field>
            <Button type="submit" size="lg" className="w-full" loading={pending}>Send reset link</Button>
          </form>
        )}
        <Link to="/login" className="mt-6 inline-block text-sm font-medium text-brand-blue hover:underline">Back to sign in</Link>
      </section>
    </main>
  );
}
