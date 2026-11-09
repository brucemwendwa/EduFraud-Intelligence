import { CheckCircle2, Info, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { TransactionDetail } from '@/api/types';
import { IndicatorList } from '@/components/risk/IndicatorList';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog, Drawer } from '@/components/ui/Dialog';
import { Detail, DetailList, SectionTitle } from '@/components/ui/DetailList';
import { LocationText } from '@/components/ui/Location';
import { RiskBadge, RiskScoreRing, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, ErrorState } from '@/components/ui/States';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { dateTime, label, money } from '@/lib/format';
import { P } from '@/lib/permissions';
import { accountStatusTone, securityEventLabel, transactionReviewTone, transactionStatusTone } from '@/lib/status';
import { useReviewTransaction, useTransaction } from './api';

export function TransactionDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { can } = useAuth();
  const { data: t, isLoading, error, refetch } = useTransaction(id);
  const review = useReviewTransaction();
  const [decision, setDecision] = useState<'cleared' | 'suspicious' | null>(null);

  const submit = (note: string) =>
    t &&
    decision &&
    review.mutate(
      { id: t.id, decision, note },
      {
        onSuccess: (res) => {
          toast.success(decision === 'cleared' ? 'Marked as legitimate' : 'Marked suspicious', { description: `${res.reference} · account re-scored` });
          setDecision(null);
        },
        onError: (err) => toast.error('Review not saved', { description: errorMessage(err) }),
      },
    );

  const footer =
    t && can(P.transactionsReview) ? (
      <>
        {t.review_status !== 'cleared' && <Button variant="secondary" icon={<CheckCircle2 className="size-4" />} onClick={() => setDecision('cleared')}>Legitimate</Button>}
        {t.review_status !== 'suspicious' && <Button variant="danger" icon={<ShieldAlert className="size-4" />} onClick={() => setDecision('suspicious')}>Suspicious</Button>}
      </>
    ) : undefined;

  return (
    <Drawer open={Boolean(id)} onOpenChange={(o) => !o && onClose()} title={t ? `${t.reference} · ${t.merchant_name}` : 'Transaction'} description={t ? `${t.organization.name} · provider event` : undefined} footer={footer} className="max-w-xl">
      {isLoading ? <CardSkeleton /> : error || !t ? <ErrorState error={error} onRetry={() => refetch()} /> : <Body t={t} />}
      <ConfirmDialog
        open={decision !== null}
        onOpenChange={(o) => !o && setDecision(null)}
        title={decision === 'cleared' ? 'Record this transaction as legitimate?' : 'Record this transaction as suspicious?'}
        description="This is a human review decision. It is audited and feeds back into the account's risk assessment. It does not block the card."
        reasonLabel="What you checked"
        tone={decision === 'suspicious' ? 'danger' : 'primary'}
        confirmLabel="Save review"
        loading={review.isPending}
        onConfirm={submit}
      />
    </Drawer>
  );
}

function Body({ t }: { t: TransactionDetail }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        {t.risk_score != null && <RiskScoreRing score={t.risk_score} level={(t.risk_level ?? 'low') as RiskLevel} size={80} />}
        <div className="space-y-1.5">
          <p className="tabular text-2xl font-semibold tracking-tight text-slate-900">{money(t.amount, true)}</p>
          <div className="flex flex-wrap gap-1.5">
            <StatusBadge value={t.status} map={transactionStatusTone} />
            <StatusBadge value={t.review_status} map={transactionReviewTone} />
            {t.risk_level && <RiskBadge level={t.risk_level as RiskLevel} />}
          </div>
          {t.decline_reason && <p className="text-xs font-medium text-red-700">Declined: {t.decline_reason}</p>}
        </div>
      </div>

      <DetailList>
        <Detail label="Account"><Link className="text-brand-blue hover:underline" to={`/app/accounts/${t.account_id}`}>{t.account_ref}</Link> <StatusBadge value={t.account_status} map={accountStatusTone} /></Detail>
        <Detail label="Student">{t.student.student_ref} · {t.student.masked_name}</Detail>
        <Detail label="Merchant category">{label(t.merchant_category)}</Detail>
        <Detail label="Channel">{label(t.channel)} · {label(t.transaction_type)}</Detail>
        <Detail label="When">{dateTime(t.occurred_at)}</Detail>
        <Detail label="Location"><LocationText location={t.location} restricted={t.location_restricted} /></Detail>
        <Detail label="Card">{t.card_ref ?? 'No card (online / transfer)'}</Detail>
        {t.destination && <Detail label="Destination"><code className="text-xs">{t.destination.handle}</code> {label(t.destination.destination_type)}</Detail>}
      </DetailList>

      <section>
        <SectionTitle>Risk indicators</SectionTitle>
        <IndicatorList indicators={t.indicators} empty="No risk indicators: this matches the student's usual activity." />
        <p className="mt-3 flex gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Unusual locations and amounts are context, not proof. Students travel, study abroad and make one-off purchases; a person decides.
        </p>
      </section>

      {t.review_note && (
        <div className="rounded-lg border border-slate-200 p-3.5 text-sm">
          <p className="text-xs text-slate-500">Reviewed by {t.reviewed_by} · {dateTime(t.reviewed_at)}</p>
          <p className="mt-1 text-slate-800">{t.review_note}</p>
        </div>
      )}

      {t.alerts.length > 0 && (
        <section>
          <SectionTitle>Alerts</SectionTitle>
          <ul className="space-y-1.5">
            {t.alerts.map((a) => (
              <li key={a.id}><Link className="text-sm text-brand-blue hover:underline" to={`/app/alerts?selected=${a.id}`}>{a.reference} · {a.title}</Link></li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <SectionTitle>Account security events (24 h before)</SectionTitle>
        {t.related_events.length === 0 ? (
          <p className="text-sm text-slate-500">No sign-in or recovery events around this transaction.</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {t.related_events.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2 px-3.5 py-2.5 text-sm">
                <span className="flex-1 text-slate-800">{securityEventLabel[e.event_type] ?? label(e.event_type)}</span>
                {e.device && <Badge tone={e.device.trust_status === 'trusted' ? 'success' : 'warning'}>{e.device.label}</Badge>}
                <span className="text-xs text-slate-500">{dateTime(e.occurred_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <SectionTitle>Recent activity on this account</SectionTitle>
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          {t.recent_transactions.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-x-3 px-3.5 py-2 text-sm">
              <span className="flex-1 truncate text-slate-800">{r.merchant_name}</span>
              <span className="tabular text-slate-700">{money(r.amount, true)}</span>
              <span className="text-xs text-slate-500">{dateTime(r.occurred_at)}</span>
              <span className="text-xs"><LocationText location={r.location} restricted={r.location_restricted} /></span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
