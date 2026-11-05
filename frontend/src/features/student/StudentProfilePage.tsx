import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, UserRound } from 'lucide-react';
import type { FormEvent } from 'react';
import { Link, Navigate } from 'react-router';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Field, Input } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { ErrorState } from '@/components/ui/States';
import { Spinner } from '@/components/ui/Spinner';
import { api, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Profile = { email: string; full_name: string; student_ref: string; organization: { name: string }; state_of_residence: string; biometric_consent: boolean; account_status: 'active' | 'inactive' };

export default function StudentProfilePage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const profile = useQuery({ queryKey: ['student-profile'], queryFn: async () => (await api.get<Profile>('/student-profile/me')).data });
  const update = useMutation({
    mutationFn: async (body: { state_of_residence: string; biometric_consent: boolean }) =>
      (await api.patch<Profile>('/student-profile/me', body)).data,
    onSuccess: (data) => { qc.setQueryData(['student-profile'], data); toast.success('Profile updated'); },
  });
  if (user?.role.key !== 'student') return <Navigate to="/app" replace />;
  if (profile.isLoading) return <div className="flex min-h-dvh items-center justify-center"><Spinner label="Loading profile" /></div>;
  if (!profile.data) return <ErrorState error={profile.error} onRetry={() => void profile.refetch()} />;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    update.mutate({
      state_of_residence: String(fields.get('state_of_residence') ?? '').toUpperCase(),
      biometric_consent: fields.get('biometric_consent') === 'on',
    });
  };
  const p = profile.data;
  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <PageHeader title="My profile" description={`${p.organization.name} · ${p.student_ref}`} actions={<Link to="/student"><Button variant="secondary">Back to aid dashboard</Button></Link>} />
      <Card className="mt-6"><CardHeader title="Account details" icon={<UserRound className="size-5" />} /><CardBody className="grid gap-4 sm:grid-cols-2">
        <div><p className="text-xs text-slate-500">Name</p><p className="font-medium text-slate-900">{p.full_name}</p></div>
        <div><p className="text-xs text-slate-500">Email</p><p className="font-medium text-slate-900">{p.email}</p></div>
        <div><p className="text-xs text-slate-500">Account status</p><p className="inline-flex items-center gap-1 font-medium text-emerald-700"><CheckCircle2 className="size-4" /> {p.account_status}</p></div>
      </CardBody></Card>
      <Card className="mt-6"><CardHeader title="Permitted profile settings" description="For name or identity corrections, contact your institution." /><CardBody>
        <form key={p.student_ref} className="space-y-5" onSubmit={submit}>
          <Field label="State of residence">{(id) => <Input id={id} name="state_of_residence" defaultValue={p.state_of_residence} maxLength={2} />}</Field>
          <label className="flex gap-3 rounded-lg border border-slate-200 p-4 text-sm text-slate-700"><input name="biometric_consent" type="checkbox" defaultChecked={p.biometric_consent} className="mt-0.5 size-4" /><span><strong className="block text-slate-900">Consent to simulated biometric verification</strong>EduShield does not store biometric images or templates. You can withdraw consent at any time and use an officer-led alternative.</span></label>
          {update.isError && <p role="alert" className="text-sm text-red-700">{errorMessage(update.error)}</p>}
          <Button type="submit" loading={update.isPending}>Save profile</Button>
        </form>
      </CardBody></Card>
    </main>
  );
}
