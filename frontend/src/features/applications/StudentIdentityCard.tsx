import { Eye, EyeOff, Fingerprint, KeyRound, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import type { StudentDetail } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { P } from '@/lib/permissions';
import { useRevealStudent } from './api';

/** Masked by default. Revealing requires `pii:reveal` and a justification, recorded as a data-access audit event. */
export function StudentIdentityCard({ student }: { student: StudentDetail }) {
  const { can } = useAuth();
  const [confirm, setConfirm] = useState(false);
  const [revealed, setRevealed] = useState<string | null>(null);
  const reveal = useRevealStudent();

  const onReveal = (reason: string) =>
    reveal.mutate(
      { studentId: student.id, reason },
      {
        onSuccess: (res) => {
          setRevealed(`${res.first_name} ${res.last_name}`);
          setConfirm(false);
          toast.success('Name revealed', { description: res.notice });
        },
        onError: (err) => toast.error('Could not reveal name', { description: errorMessage(err) }),
      },
    );

  return (
    <Card>
      <CardHeader
        title="Student identity"
        description="Identity attributes are stored only as keyed tokens."
        icon={<KeyRound className="size-4" />}
      />
      <CardBody className="space-y-4">
        <div className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
          <div className="min-w-0">
            <p className="text-xs text-slate-500">Name</p>
            <p className="truncate font-medium text-slate-900">{revealed ?? student.masked_name}</p>
          </div>
          {revealed ? (
            <Button variant="ghost" size="sm" icon={<EyeOff className="size-3.5" />} onClick={() => setRevealed(null)}>
              Hide
            </Button>
          ) : (
            can(P.piiReveal) && (
              <Button variant="secondary" size="sm" icon={<Eye className="size-3.5" />} onClick={() => setConfirm(true)}>
                Reveal
              </Button>
            )
          )}
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-slate-500">Student reference</dt>
            <dd className="font-mono text-xs text-slate-800">{student.student_ref}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Birth year</dt>
            <dd className="tabular text-slate-800">{student.birth_year}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">State of residence</dt>
            <dd className="text-slate-800">{student.state_of_residence}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Biometric consent</dt>
            <dd>
              {student.biometric_consent ? (
                <Badge tone="success" icon={<Fingerprint className="size-3" />}>Consented</Badge>
              ) : (
                <Badge tone="neutral" icon={<ShieldCheck className="size-3" />}>Alternative only</Badge>
              )}
            </dd>
          </div>
        </dl>
      </CardBody>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Reveal student name"
        description="Names are masked to minimise exposure of personal data. State why you need it; your access is recorded in the audit trail."
        reasonLabel="Business justification"
        confirmLabel="Reveal name"
        loading={reveal.isPending}
        onConfirm={onReveal}
      />
    </Card>
  );
}
