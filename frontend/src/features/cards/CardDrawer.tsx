import { AlertTriangle, Ban, CreditCard, PackageCheck, RefreshCcw, ShieldCheck, Siren } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { toast } from 'sonner';
import type { CardDetail } from '@/api/types';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog, Drawer, Modal } from '@/components/ui/Dialog';
import { Detail, DetailList, SectionTitle } from '@/components/ui/DetailList';
import { Field, Select, Textarea } from '@/components/ui/Field';
import { LocationText } from '@/components/ui/Location';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, ErrorState } from '@/components/ui/States';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { date, dateTime, label, money } from '@/lib/format';
import { P } from '@/lib/permissions';
import { cardStatusTone, securityEventLabel, transactionStatusTone } from '@/lib/status';
import { useCard, useCardAction, type CardAction } from './api';

const NOTE_ACTIONS: Partial<Record<CardAction, { title: string; description: string; confirm: string; tone: 'danger' | 'primary'; label: string }>> = {
  block: {
    title: 'Ask the provider to block this card?',
    description: 'All further authorisations are declined by the provider. A blocked card is never re-activated; the student receives a replacement after identity verification.',
    confirm: 'Request block',
    tone: 'danger',
    label: 'Reason',
  },
  'suspicious-activity': {
    title: 'Record suspicious card activity',
    description: 'Adds a card security event and re-scores the account. It does not block the card.',
    confirm: 'Record',
    tone: 'primary',
    label: 'What was observed',
  },
  'request-replacement': {
    title: 'Request a replacement card?',
    description: 'The replacement is issued only after the student’s identity has been re-verified.',
    confirm: 'Request replacement',
    tone: 'primary',
    label: 'Note',
  },
};

export function CardDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { can } = useAuth();
  const { data: c, isLoading, error, refetch } = useCard(id);
  const action = useCardAction();
  const [pending, setPending] = useState<CardAction | null>(null);
  const [lost, setLost] = useState(false);

  const run = (kind: CardAction, body?: unknown, done?: string) =>
    c &&
    action.mutate(
      { id: c.id, action: kind, body },
      {
        onSuccess: (res) => {
          toast.success(done ?? 'Recorded', { description: `${res.reference} · provider acknowledgement and audit event stored` });
          setPending(null);
          setLost(false);
        },
        onError: (err) => toast.error('Card action failed', { description: errorMessage(err) }),
      },
    );

  const manage = can(P.cardsManage);
  const footer = c && manage && (
    <>
      {c.status === 'active' && <Button variant="danger" icon={<Siren className="size-4" />} onClick={() => setLost(true)}>Report lost or stolen</Button>}
      {(c.status === 'active' || c.status === 'reported_lost') && <Button variant="secondary" icon={<Ban className="size-4" />} onClick={() => setPending('block')}>Block card</Button>}
      {(c.status === 'reported_lost' || c.status === 'blocked') && <Button variant="secondary" icon={<RefreshCcw className="size-4" />} onClick={() => setPending('request-replacement')}>Request replacement</Button>}
      {c.status === 'replacement_requested' && (
        <Button icon={<PackageCheck className="size-4" />} disabled={!c.verified_since_report} loading={action.isPending} onClick={() => run('issue-replacement', undefined, 'Replacement issued by the provider')}
          title={c.verified_since_report ? undefined : 'Identity must be verified first'}>
          Issue replacement
        </Button>
      )}
      {c.status !== 'replaced' && <Button variant="ghost" icon={<AlertTriangle className="size-4" />} onClick={() => setPending('suspicious-activity')}>Record suspicious activity</Button>}
    </>
  );

  const config = pending ? NOTE_ACTIONS[pending] : undefined;
  return (
    <Drawer open={Boolean(id)} onOpenChange={(o) => !o && onClose()} title={c ? `Student ID card ${c.masked_number}` : 'Student ID card'} description={c ? `${c.reference} · ${c.organization.name}` : undefined} footer={footer || undefined} className="max-w-xl">
      {isLoading ? <CardSkeleton /> : error || !c ? <ErrorState error={error} onRetry={() => refetch()} /> : <Body c={c} />}
      {config && (
        <ConfirmDialog
          open={pending !== null}
          onOpenChange={(o) => !o && setPending(null)}
          title={config.title}
          description={config.description}
          reasonLabel={config.label}
          tone={config.tone}
          confirmLabel={config.confirm}
          loading={action.isPending}
          onConfirm={(note) => pending && run(pending, { note }, config.confirm)}
        />
      )}
      {c && <ReportLostDialog open={lost} onOpenChange={setLost} loading={action.isPending} onSubmit={(body) => run('report-lost', body, 'Card reported lost and blocked')} />}
    </Drawer>
  );
}

function Body({ c }: { c: CardDetail }) {
  return (
    <div className="space-y-6">
      <div className="relative overflow-hidden rounded-xl bg-gradient-to-br from-navy-900 via-navy-800 to-navy-600 p-5 text-white shadow-raised">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-[11px] tracking-wider text-navy-200 uppercase">{c.organization.name}</p>
            <p className="mt-1 text-sm font-medium">University ID · access credential</p>
          </div>
          <CreditCard className="size-6 text-navy-200" aria-hidden />
        </div>
        <p className="tabular mt-6 font-mono text-lg tracking-widest">{c.masked_number}</p>
        <div className="mt-3 flex items-end justify-between text-xs text-navy-100">
          <span>{c.student.student_ref} · {c.student.masked_name}</span>
          <span>Expires {date(c.expires_on as string)}</span>
        </div>
        <p className="mt-3 text-[10px] text-navy-200">The card stores no money. Funds are held by the payment-provider partner.</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge value={c.status} map={cardStatusTone} />
        {c.verified_since_report && <Badge tone="success" icon={<ShieldCheck className="size-3" />}>Identity verified since report</Badge>}
        {c.block_confirmation && <Badge tone="neutral">Provider ack {c.block_confirmation}</Badge>}
      </div>

      <DetailList>
        <Detail label="Linked account">{c.account_id ? <Link className="text-brand-blue hover:underline" to={`/app/accounts/${c.account_id}`}>{c.account_ref}</Link> : 'Not linked'}</Detail>
        <Detail label="Issued">{date(c.issued_at)}</Detail>
        <Detail label="Reported lost">{c.reported_lost_at ? `${dateTime(c.reported_lost_at)} · ${label(c.report_channel)}` : '—'}</Detail>
        <Detail label="Blocked at provider">{dateTime(c.blocked_at)}</Detail>
        <Detail label="Replacement requested">{dateTime(c.replacement_requested_at)}</Detail>
        <Detail label="Replaced by">{c.replaced_by_ref ?? '—'}</Detail>
      </DetailList>

      <section>
        <SectionTitle>Card security events</SectionTitle>
        {c.security_events.length === 0 ? (
          <p className="text-sm text-slate-500">No card security events.</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {c.security_events.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2 px-3.5 py-2.5 text-sm">
                <span className="flex-1 font-medium text-slate-800">{securityEventLabel[e.event_type] ?? label(e.event_type)}</span>
                <span className="text-xs text-slate-500">{label(e.source)} · {dateTime(e.occurred_at)}</span>
                {e.note && <p className="w-full text-xs text-slate-600">{e.note}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <SectionTitle>Usage history</SectionTitle>
        {c.usage.length === 0 ? (
          <p className="text-sm text-slate-500">No authorised transactions on this card.</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {c.usage.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 py-2.5 text-sm">
                <Link to={`/app/transactions?selected=${t.id}`} className="font-medium text-slate-800 hover:text-brand-blue">{t.merchant_name}</Link>
                <span className="tabular text-slate-700">{money(t.amount, true)}</span>
                <span className="text-xs text-slate-500">{dateTime(t.occurred_at)}</span>
                <span className="text-xs"><LocationText location={t.location} restricted={t.location_restricted} /></span>
                <span className="ml-auto flex gap-1.5">
                  <StatusBadge value={t.status} map={transactionStatusTone} />
                  {t.risk_level && t.risk_level !== 'low' && <RiskBadge level={t.risk_level as RiskLevel} score={t.risk_score} />}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {c.history.length > 0 && (
        <section>
          <SectionTitle>Other cards for this student</SectionTitle>
          <ul className="space-y-1.5 text-sm">
            {c.history.map((h) => (
              <li key={h.id} className="flex items-center gap-2"><code className="text-xs">{h.masked_number}</code><span className="text-slate-600">{h.reference}</span><StatusBadge value={h.status} map={cardStatusTone} /></li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function ReportLostDialog({ open, onOpenChange, onSubmit, loading }: { open: boolean; onOpenChange: (o: boolean) => void; onSubmit: (body: unknown) => void; loading: boolean }) {
  const [channel, setChannel] = useState('phone');
  const [note, setNote] = useState('');
  const [block, setBlock] = useState(true);
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Report card lost or stolen"
      description="Records the report, asks the provider to block the card, holds sensitive account changes and opens an identity verification request."
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>Cancel</Button>
          <Button variant="danger" loading={loading} onClick={() => onSubmit({ channel, note: note.trim() || null, block })}>Record report</Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Reported via">
          {(id) => (
            <Select id={id} value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="phone">Phone call</option>
              <option value="in_person">In person</option>
              <option value="student_portal">Student portal</option>
              <option value="officer">Officer observation</option>
            </Select>
          )}
        </Field>
        <Field label="Note (optional)">
          {(id) => <Textarea id={id} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" className="size-4 rounded border-slate-300" checked={block} onChange={(e) => setBlock(e.target.checked)} />
          Ask the provider to block the card now (recommended)
        </label>
      </div>
    </Modal>
  );
}
