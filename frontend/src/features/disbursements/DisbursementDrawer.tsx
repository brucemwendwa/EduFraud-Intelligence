import { ArrowUpRight, PauseCircle, PlayCircle, ShieldAlert } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { DisbursementRow } from '@/api/types';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog, Drawer } from '@/components/ui/Dialog';
import { RiskBadge, riskLevelOf } from '@/components/ui/Risk';
import { CardSkeleton, ErrorState } from '@/components/ui/States';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { date, dateTime, label, money } from '@/lib/format';
import { P } from '@/lib/permissions';
import { disbursementStatusTone } from '@/lib/status';
import { useDisbursement, useHoldAction } from './api';

export function DisbursementDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { can } = useAuth();
  const { data: d, isLoading, error, refetch } = useDisbursement(id);
  const action = useHoldAction();
  const [confirm, setConfirm] = useState<'hold' | 'release' | null>(null);

  const run = (reason: string) => {
    if (!d || !confirm) return;
    action.mutate(
      { id: d.id, action: confirm, reason },
      {
        onSuccess: (res) => {
          toast.success(confirm === 'hold' ? 'Disbursement held' : 'Hold released', {
            description: `${res.reference} · ${money(res.amount, true)}`,
          });
          setConfirm(null);
        },
        onError: (err) => toast.error('Action failed', { description: errorMessage(err) }),
      },
    );
  };

  const footer =
    d && can(P.disbursementsHold) ? (
      d.status === 'scheduled' ? (
        <Button variant="danger" icon={<PauseCircle className="size-4" />} onClick={() => setConfirm('hold')}>Hold disbursement</Button>
      ) : d.status === 'held' ? (
        <Button icon={<PlayCircle className="size-4" />} onClick={() => setConfirm('release')}>Release hold</Button>
      ) : undefined
    ) : undefined;

  return (
    <Drawer open={Boolean(id)} onOpenChange={(o) => !o && onClose()} title={d?.reference ?? 'Disbursement'} description={d ? `${label(d.fund_type)} · ${d.organization.name}` : undefined} footer={footer}>
      {isLoading ? (
        <CardSkeleton />
      ) : error || !d ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : (
        <div className="space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="tabular text-3xl font-semibold tracking-tight text-slate-900">{money(d.amount, true)}</p>
              <p className="mt-1 text-sm text-slate-500">{d.status === 'scheduled' ? 'Scheduled for' : 'Disbursed'} {dateTime(d.disbursed_at)}</p>
            </div>
            <div className="flex flex-col items-end gap-1.5">
              <StatusBadge value={d.status} map={disbursementStatusTone} />
              {d.risk_score != null && <RiskBadge level={riskLevelOf(d.risk_score)} score={d.risk_score} />}
            </div>
          </div>

          {d.hold_reason && (
            <div className="rounded-lg bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900 ring-1 ring-amber-100">
              <span className="font-medium">On hold:</span> {d.hold_reason}
            </div>
          )}

          {d.risk_flags.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold tracking-wider text-slate-500 uppercase">Risk indicators</h3>
              <ul className="space-y-1.5">
                {d.risk_flags.map((f) => (
                  <li key={f} className="flex gap-2 text-sm text-slate-700">
                    <ShieldAlert className="mt-0.5 size-4 shrink-0 text-risk-high" aria-hidden />{f}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wider text-slate-500 uppercase">Payment destination</h3>
            <dl className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 p-3.5 text-sm">
              <Item label="Token"><code className="text-xs">{d.destination.handle}</code></Item>
              <Item label="Type">{label(d.destination.destination_type)} ••{d.destination.display_suffix}</Item>
              <Item label="Students using it (your scope)">
                <span className={d.destination_usage.students_in_scope > 1 ? 'font-semibold text-red-700' : undefined}>{d.destination_usage.students_in_scope}</span>
              </Item>
              <Item label="At other institutions">
                <span className={d.destination_usage.students_other_institutions > 0 ? 'font-semibold text-red-700' : undefined}>{d.destination_usage.students_other_institutions}</span>
              </Item>
              <Item label="First seen">{date(d.destination_usage.first_seen_at)}</Item>
              <Item label="Changed before payout">{d.destination_changed_at ? dateTime(d.destination_changed_at) : 'No'}</Item>
            </dl>
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wider text-slate-500 uppercase">Student & application</h3>
            <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3.5 text-sm">
              <div>
                <p className="font-mono text-xs text-slate-700">{d.student.student_ref}</p>
                <p className="text-xs text-slate-500">{d.student.masked_name}</p>
              </div>
              {d.application_id && (
                <Link to={`/app/applications/${d.application_id}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-blue hover:underline">
                  {d.application_ref} <ArrowUpRight className="size-3.5" />
                </Link>
              )}
            </div>
          </section>

          <MiniList title="Other payments to this destination" rows={d.same_destination} empty="No other disbursements in your scope use this destination." />
          <MiniList title="This student's other disbursements" rows={d.student_disbursements} empty="No other disbursements." />
        </div>
      )}
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm === 'hold' ? 'Hold this disbursement?' : 'Release this hold?'}
        description={confirm === 'hold' ? 'Funds will not be released until a person releases the hold.' : 'The disbursement returns to the payment schedule.'}
        reasonLabel="Reason"
        tone={confirm === 'hold' ? 'danger' : 'primary'}
        confirmLabel={confirm === 'hold' ? 'Hold funds' : 'Release hold'}
        loading={action.isPending}
        onConfirm={run}
      />
    </Drawer>
  );
}

function Item({ label: name, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{name}</dt>
      <dd className="mt-0.5 text-slate-800">{children}</dd>
    </div>
  );
}

function MiniList({ title, rows, empty }: { title: string; rows: DisbursementRow[]; empty: string }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold tracking-wider text-slate-500 uppercase">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 px-3.5 py-2.5 text-sm">
              <span className="font-medium text-slate-800">{r.reference}</span>
              <span className="font-mono text-xs text-slate-500">{r.student.student_ref}</span>
              <span className="tabular text-slate-700">{money(r.amount)}</span>
              <span className="hidden text-xs text-slate-500 sm:inline">{date(r.disbursed_at)}</span>
              {r.status === 'held' && <Badge tone="warning">Held</Badge>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
