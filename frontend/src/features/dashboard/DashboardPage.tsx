import { PageHeader } from '@/components/ui/PageHeader';
import { useAuth } from '@/lib/auth';

export default function DashboardPage() {
  const { user } = useAuth();
  return (
    <PageHeader
      title="Fraud intelligence dashboard"
      description={`Signed in as ${user?.full_name ?? ''}. Dashboard analytics are wired to the API in Phase 10.`}
    />
  );
}
