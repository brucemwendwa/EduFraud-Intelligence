import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Building2, KeyRound, Lock, Mail, ShieldCheck } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Logo } from '@/components/layout/Logo';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { api, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export function LoginPage() {
  const { user, login, demoLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/app';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);

  const demo = useQuery({
    queryKey: ['auth', 'demo-accounts'],
    queryFn: async () => (await api.get('/auth/demo-accounts')).data,
    retry: false,
    staleTime: Infinity,
  });

  if (user) return <Navigate to={from} replace />;

  const signIn = async (mail: string, pass: string) => {
    setError(null);
    setPending(mail);
    try {
      const me = await login(mail, pass);
      toast.success(`Welcome, ${me.full_name.split(' ')[0]}`, { description: `Signed in as ${me.role.name}` });
      navigate(me.role.key === 'student' ? '/student' : from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(null);
    }
  };

  const enterDemo = async () => {
    setError(null);
    setPending('demo');
    try {
      await demoLogin();
      toast.success('Demo session started', { description: 'Synthetic data · restricted presenter permissions' });
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(null);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Enter your email address and password.');
      return;
    }
    void signIn(email.trim(), password);
  };

  return (
    <div className="grid min-h-dvh lg:grid-cols-[1fr_1.1fr]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-navy-950 p-10 text-white lg:flex">
        <div aria-hidden className="absolute -right-32 -bottom-32 size-[28rem] rounded-full bg-brand-blue/20 blur-3xl" />
        <Link to="/" aria-label="EduShield AI home">
          <Logo tone="light" />
        </Link>
        <div className="relative max-w-md">
          <h1 className="text-3xl leading-tight font-semibold tracking-tight">
            Explainable fraud intelligence for the people who protect student aid.
          </h1>
          <ul className="mt-8 space-y-4 text-sm text-navy-100/85">
            {[
              [ShieldCheck, 'Every high-risk decision stays with a human reviewer'],
              [Lock, 'Institution-level data isolation and role-based access'],
              [KeyRound, 'Identity attributes tokenized. No SSNs or bank numbers are stored'],
            ].map(([Icon, text]) => {
              const I = Icon as typeof ShieldCheck;
              return (
                <li key={text as string} className="flex gap-3">
                  <I className="size-5 shrink-0 text-blue-300" aria-hidden />
                  {text as string}
                </li>
              );
            })}
          </ul>
        </div>
        <p className="relative text-xs text-navy-200/60">
          Prototype · synthetic demonstration data · not connected to FSA or FAFSA systems
        </p>
      </aside>

      <main className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-md">
          <Link to="/" className="mb-10 inline-block lg:hidden" aria-label="EduShield AI home">
            <Logo />
          </Link>
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Sign in</h2>
          <p className="mt-1.5 text-sm text-slate-500">Use your institutional EduShield AI account.</p>

          <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
            <Field label="Email address">
              {(id) => (
                <Input
                  id={id}
                  type="email"
                  autoComplete="username"
                  icon={<Mail className="size-4" />}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@institution.edu"
                  aria-invalid={Boolean(error) || undefined}
                />
              )}
            </Field>
            <Field label="Password">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  autoComplete="current-password"
                  icon={<Lock className="size-4" />}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-invalid={Boolean(error) || undefined}
                />
              )}
            </Field>
            {error && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-100">
                {error}
              </p>
            )}
            <Button type="submit" size="lg" className="w-full" loading={pending === email.trim() && pending !== null}>
              Sign in <ArrowRight className="size-4" aria-hidden />
            </Button>
          </form>

          {demo.data && demo.data.length > 0 && (
            <section className="mt-10" aria-labelledby="demo-heading">
              <h3 id="demo-heading" className="text-xs font-semibold tracking-wider text-slate-500 uppercase">Hackathon demo</h3>
              <Button type="button" size="lg" className="mt-3 w-full" loading={pending === 'demo'} onClick={() => void enterDemo()}>
                <Building2 className="size-4" aria-hidden /> Enter Demo <ArrowRight className="size-4" aria-hidden />
              </Button>
              <p className="mt-2 text-xs text-slate-500">Synthetic data only. Demo sessions are disabled outside DEMO_MODE.</p>
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
