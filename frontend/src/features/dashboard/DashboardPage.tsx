import { ArrowRight, Banknote, Bell, Cpu, FileSearch, ScanFace, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router';
import { Card } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { useAuth } from '@/lib/auth';
import { P, type Permission } from '@/lib/permissions';

const modules: { to: string; icon: LucideIcon; title: string; body: string; permission: Permission }[] = [
  { to: '/app/alerts', icon: Bell, title: 'Fraud alerts', body: 'High and critical risks waiting for a person to review.', permission: P.alertsRead },
  { to: '/app/applications', icon: FileSearch, title: 'Applications', body: 'Search applications and open an explained risk score.', permission: P.applicationsRead },
  { to: '/app/verification', icon: ScanFace, title: 'Identity verification', body: 'Run a simulated step-up check or record an in-person one.', permission: P.verificationsRead },
  { to: '/app/disbursements', icon: Banknote, title: 'Disbursements', body: 'Monitor refunds and hold or release a payment.', permission: P.disbursementsRead },
  { to: '/app/engine', icon: Cpu, title: 'Detection engine', body: 'Rules, model card, scenario coverage and detection runs.', permission: P.dashboardRead },
];

export default function DashboardPage() {
  const { user, can } = useAuth();
  return (
    <>
      <PageHeader
        title="Fraud intelligence dashboard"
        description={`Signed in as ${user?.full_name ?? ''}. Portfolio charts for this page are planned; the modules below are working now.`}
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {modules
          .filter((m) => can(m.permission))
          .map((m) => (
            <Link key={m.to} to={m.to} className="group rounded-xl focus-visible:outline-2 focus-visible:outline-brand-blue">
              <Card className="flex h-full items-start gap-4 p-5 transition-colors group-hover:border-navy-200">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-navy-50 text-navy-700">
                  <m.icon className="size-5" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-sm font-semibold text-slate-900">
                    {m.title}
                    <ArrowRight className="size-3.5 text-slate-400 transition-transform group-hover:translate-x-0.5" aria-hidden />
                  </span>
                  <span className="mt-1 block text-sm text-slate-600">{m.body}</span>
                </span>
              </Card>
            </Link>
          ))}
      </div>
    </>
  );
}
