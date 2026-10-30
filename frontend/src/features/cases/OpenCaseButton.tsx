import { FolderKanban, FolderOpen } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { ApiError, errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { P } from '@/lib/permissions';
import { useOpenCase } from './api';

interface Props {
  applicationId?: string | null;
  alertId?: string | null;
  /** When a case already exists, the button links to it instead. */
  caseId?: string | null;
  caseRef?: string | null;
  size?: 'sm' | 'md';
}

/** Hands an alert or application over to a human investigation. */
export function OpenCaseButton({ applicationId, alertId, caseId, caseRef, size = 'md' }: Props) {
  const { can } = useAuth();
  const navigate = useNavigate();
  const open = useOpenCase();

  if (caseId) {
    return can(P.casesRead) ? (
      <Button variant="secondary" size={size} icon={<FolderOpen className="size-4" />} onClick={() => navigate(`/app/cases/${caseId}`)}>
        View {caseRef ?? 'case'}
      </Button>
    ) : null;
  }
  if (!can(P.casesCreate) || (!applicationId && !alertId)) return null;

  const start = () =>
    open.mutate(
      { ...(applicationId ? { application_id: applicationId } : {}), ...(alertId ? { alert_id: alertId } : {}) },
      {
        onSuccess: (c) => {
          toast.success(`${c.reference} opened`, {
            description: `${c.evidence.length} supporting record(s) attached. Assign it and start the review.`,
          });
          navigate(`/app/cases/${c.id}`);
        },
        onError: (err) => {
          const existing = err instanceof ApiError ? (err.details as { case_id?: string } | undefined)?.case_id : undefined;
          if (existing) {
            toast.info('A case is already open', { description: errorMessage(err) });
            navigate(`/app/cases/${existing}`);
          } else {
            toast.error('Could not open a case', { description: errorMessage(err) });
          }
        },
      },
    );

  return (
    <Button size={size} icon={<FolderKanban className="size-4" />} loading={open.isPending} onClick={start}>
      Open investigation
    </Button>
  );
}
