import { useQuery } from '@tanstack/react-query';
import { GraduationCap } from 'lucide-react';
import { Navigate } from 'react-router';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { Spinner } from '@/components/ui/Spinner';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Portal = { student_ref: string; applications: { reference: string; status: string; program: string; requested_amount: string; risk_level: string | null }[] };

export default function StudentDashboardPage() {
  const { user } = useAuth();
  const portal = useQuery({ queryKey: ['student-portal'], queryFn: async () => (await api.get<Portal>('/student-portal/me')).data });
  if (user?.role.key !== 'student') return <Navigate to="/app" replace />;
  if (portal.isLoading) return <Spinner label="Loading your aid information" className="size-6" />;
  if (!portal.data) return <p className="text-sm text-red-700">Unable to load your aid information.</p>;
  return <>
    <PageHeader title="My financial aid" description={`Synthetic student record · ${portal.data.student_ref}`} />
    <Card><CardHeader title="Applications" icon={<GraduationCap className="size-5" />} /><CardBody>
      <ul className="space-y-3">{portal.data.applications.map((app) => <li key={app.reference} className="flex justify-between gap-4 border-b border-slate-100 pb-3 text-sm"><span><strong>{app.reference}</strong><br /><span className="text-slate-500">{app.program}</span></span><span className="text-right"><strong className="capitalize">{app.status.replace('_', ' ')}</strong><br /><span className="text-slate-500">${Number(app.requested_amount).toLocaleString()}</span></span></li>)}</ul>
    </CardBody></Card>
  </>;
}
