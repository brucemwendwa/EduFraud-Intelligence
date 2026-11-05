import { CheckCircle2, KeyRound, Lock } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { errorMessage, api } from '@/lib/api';

export default function ActivationPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(token ? null : 'This activation link is invalid or incomplete.');
  const [name, setName] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token || pending) return;
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setPending(true);
    setError(null);
    try {
      const result = (await api.post<{ full_name: string }>('/student-activation', { token, password })).data;
      setName(result.full_name);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-50 px-4 py-10">
      <section className="w-full max-w-md rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 sm:p-8">
        {name ? (
          <div className="text-center">
            <CheckCircle2 className="mx-auto size-12 text-emerald-600" aria-hidden />
            <h1 className="mt-4 text-2xl font-semibold text-slate-900">Account activated</h1>
            <p className="mt-2 text-sm text-slate-600">Welcome, {name}. Your student portal is ready.</p>
            <Link to="/login"><Button size="lg" className="mt-6 w-full">Sign in</Button></Link>
          </div>
        ) : (
          <>
            <KeyRound className="size-8 text-navy-800" aria-hidden />
            <h1 className="mt-4 text-2xl font-semibold text-slate-900">Activate your student account</h1>
            <p className="mt-2 text-sm text-slate-600">Create a password to access your institution's EduShield student portal.</p>
            <form className="mt-7 space-y-4" onSubmit={submit} noValidate>
              <Field label="Create password" hint="At least 12 characters and three of: uppercase, lowercase, number, symbol.">
                {(id) => <Input id={id} type="password" autoComplete="new-password" icon={<Lock className="size-4" />} value={password} onChange={(e) => setPassword(e.target.value)} disabled={!token} />}
              </Field>
              <Field label="Confirm password">
                {(id) => <Input id={id} type="password" autoComplete="new-password" icon={<Lock className="size-4" />} value={confirm} onChange={(e) => setConfirm(e.target.value)} disabled={!token} />}
              </Field>
              {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-100">{error}</p>}
              <Button type="submit" size="lg" className="w-full" loading={pending} disabled={!token}>Activate account</Button>
            </form>
            <p className="mt-5 text-center text-xs text-slate-500">Need help? Contact your institution's financial aid office.</p>
          </>
        )}
      </section>
    </main>
  );
}
