import {
  ArrowUpRight,
  Bell,
  Check,
  FileText,
  FolderOpen,
  MessageSquarePlus,
  Paperclip,
  Play,
  Scale,
  ScrollText,
  ShieldAlert,
  UserCheck,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';
import type { CaseDetail } from '@/api/types';
import { SignalList } from '@/components/risk/SignalList';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Textarea } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { useApplication } from '@/features/applications/api';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { cn } from '@/lib/cn';
import { date, dateTime, label } from '@/lib/format';
import { P } from '@/lib/permissions';
import { alertStatusTone, caseStatusTone, findingMeta, priorityTone } from '@/lib/status';
import { useAddNote, useCase, useStartReview } from './api';
import { AddEvidenceDialog, AssignDialog } from './CaseDialogs';
import { allowedDecisions, DecisionDialog, OUTCOMES } from './DecisionDialog';

const STEPS = ['new', 'under_review', 'escalated', 'resolved', 'closed'];

export default function CaseWorkspacePage() {
  const { id = '' } = useParams();
  const { data, isLoading, error, refetch } = useCase(id);
  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-80" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2"><CardSkeleton /></Card>
          <Card><CardSkeleton /></Card>
        </div>
      </div>
    );
  }
  if (error || !data) return <ErrorState title="Case unavailable" error={error} onRetry={() => refetch()} />;
  return <Workspace c={data} />;
}

function Workspace({ c }: { c: CaseDetail }) {
  const { can } = useAuth();
  const [dialog, setDialog] = useState<'assign' | 'decision' | 'evidence' | null>(null);
  const startReview = useStartReview(c.id);
  const closed = c.status === 'closed';
  const finding = findingMeta[c.finding];

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'Investigations', to: '/app/cases' }, { label: c.reference }]}
        title={c.title}
        description={`${c.reference} · ${label(c.fraud_category)} · opened by ${c.created_by?.full_name ?? 'system'} on ${dateTime(c.created_at)}`}
        meta={
          <>
            <StatusBadge value={c.status} map={caseStatusTone} />
            <Badge tone={priorityTone[c.priority] ?? 'neutral'}>Priority: {label(c.priority)}</Badge>
            {finding && <Badge tone={finding.tone} title={finding.help}>{finding.label}</Badge>}
            {c.overdue && <Badge tone="critical">Overdue</Badge>}
          </>
        }
        actions={
          <>
            {c.status === 'new' && can(P.casesUpdate) && (
              <Button variant="secondary" icon={<Play className="size-4" />} loading={startReview.isPending}
                onClick={() => startReview.mutate(undefined, {
                  onSuccess: () => toast.success('Review started', { description: `${c.reference} is now under review.` }),
                  onError: (err) => toast.error('Could not start review', { description: errorMessage(err) }),
                })}>
                Start review
              </Button>
            )}
            {!closed && can(P.casesAssign) && (
              <Button variant="secondary" icon={<UserCheck className="size-4" />} onClick={() => setDialog('assign')}>
                {c.assigned_to ? 'Reassign' : 'Assign'}
              </Button>
            )}
            {!closed && can(P.casesUpdate) && (
              <Button variant="secondary" icon={<Paperclip className="size-4" />} onClick={() => setDialog('evidence')}>Add evidence</Button>
            )}
            {can(P.casesResolve) && allowedDecisions(c.status).length > 0 && (
              <Button icon={<Scale className="size-4" />} onClick={() => setDialog('decision')}>Record decision</Button>
            )}
          </>
        }
      />

      <Card className="mb-6 p-5">
        <div className="grid gap-6 lg:grid-cols-2">
          <StatusStepper status={c.status} />
          <FindingLadder finding={c.finding} />
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2">
          <Card>
            <Tabs defaultValue="evidence">
              <div className="px-5 pt-2">
                <TabsList>
                  <TabsTrigger value="evidence" count={c.evidence.length}>Evidence</TabsTrigger>
                  <TabsTrigger value="risk">Risk explanation</TabsTrigger>
                  <TabsTrigger value="notes" count={c.notes.length}>Notes</TabsTrigger>
                  <TabsTrigger value="timeline" count={c.timeline.length}>Timeline</TabsTrigger>
                </TabsList>
              </div>
              <TabsContent value="evidence" className="p-5"><EvidencePanel c={c} /></TabsContent>
              <TabsContent value="risk" className="p-5"><RiskExplanation applicationId={c.application_id} /></TabsContent>
              <TabsContent value="notes" className="p-5"><NotesPanel c={c} canWrite={!closed && can(P.casesUpdate)} /></TabsContent>
              <TabsContent value="timeline" className="p-5"><Timeline c={c} /></TabsContent>
            </Tabs>
          </Card>
        </div>
        <div className="space-y-6">
          <FactsCard c={c} />
          <DecisionsCard c={c} />
          <AlertsCard c={c} />
        </div>
      </div>

      <AssignDialog c={c} open={dialog === 'assign'} onOpenChange={(o) => setDialog(o ? 'assign' : null)} />
      <AddEvidenceDialog c={c} open={dialog === 'evidence'} onOpenChange={(o) => setDialog(o ? 'evidence' : null)} />
      <DecisionDialog key={c.status} c={c} open={dialog === 'decision'} onOpenChange={(o) => setDialog(o ? 'decision' : null)} />
    </>
  );
}

function StatusStepper({ status }: { status: string }) {
  const current = STEPS.indexOf(status);
  return (
    <div>
      <h2 className="mb-3 text-xs font-semibold tracking-wider text-slate-500 uppercase">Case status</h2>
      <ol className="flex items-center gap-1.5" aria-label="Case status">
        {STEPS.map((s, i) => (
          <li key={s} className="flex flex-1 items-center gap-1.5">
            <span
              aria-current={i === current ? 'step' : undefined}
              className={cn(
                'flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
                i < current ? 'bg-navy-900 text-white' : i === current ? 'bg-navy-100 text-navy-900 ring-2 ring-navy-900' : 'bg-slate-100 text-slate-400',
              )}
            >
              {i < current ? <Check className="size-3.5" /> : i + 1}
            </span>
            <span className={cn('hidden text-xs xl:inline', i === current ? 'font-semibold text-slate-900' : 'text-slate-500')}>{label(s)}</span>
            {i < STEPS.length - 1 && <span className="h-px flex-1 bg-slate-200" aria-hidden />}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Keeps suspicion and findings visibly distinct. Only a human decision moves along this ladder. */
function FindingLadder({ finding }: { finding: string }) {
  const rungs = ['suspicious_activity', 'suspected_fraud', 'confirmed_fraud'];
  const notSubstantiated = finding === 'not_substantiated';
  return (
    <div>
      <h2 className="mb-3 text-xs font-semibold tracking-wider text-slate-500 uppercase">What has been established</h2>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {rungs.map((r, i) => (
          <span key={r} className="flex items-center gap-1.5">
            <span className={cn('rounded-md px-2 py-1 font-medium ring-1 ring-inset', r === finding ? 'bg-navy-900 text-white ring-navy-900' : 'text-slate-500 ring-slate-200')}>
              {findingMeta[r]!.label}
            </span>
            {i < rungs.length - 1 && <span className="text-slate-300" aria-hidden>→</span>}
          </span>
        ))}
        <span className="text-slate-300" aria-hidden>|</span>
        <span className={cn('rounded-md px-2 py-1 font-medium ring-1 ring-inset', notSubstantiated ? 'bg-green-700 text-white ring-green-700' : 'text-slate-500 ring-slate-200')}>
          {findingMeta.not_substantiated!.label}
        </span>
      </div>
      <p className="mt-2 text-xs text-slate-500">{findingMeta[finding]?.help}</p>
    </div>
  );
}

function EvidencePanel({ c }: { c: CaseDetail }) {
  if (c.evidence.length === 0) return <EmptyState icon={<Paperclip className="size-5" />} title="No evidence attached" description="Attach the records that support or refute the suspicion." />;
  return (
    <ul className="space-y-3">
      {c.evidence.map((e) => {
        const signals = (e.data.signals as { code: string; title: string; points: number }[] | undefined) ?? [];
        return (
          <li key={e.id} className="rounded-lg border border-slate-200 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="navy">{label(e.evidence_type)}</Badge>
              <p className="text-sm font-medium text-slate-900">{e.title}</p>
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{e.summary}</p>
            {signals.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {signals.map((s) => (
                  <li key={s.code} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700">{s.title} <span className="tabular font-semibold">+{Math.round(s.points)}</span></li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-[11px] text-slate-400">
              Attached by {e.added_by?.full_name ?? 'system'} · {dateTime(e.created_at)}{e.ref_label ? ` · ${e.ref_label}` : ''}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function RiskExplanation({ applicationId }: { applicationId: string | null }) {
  const app = useApplication(applicationId ?? '');
  if (!applicationId) return <EmptyState title="No linked application" />;
  if (app.isLoading) return <CardSkeleton />;
  if (app.error || !app.data) return <ErrorState error={app.error} onRetry={() => app.refetch()} />;
  const a = app.data.assessment;
  if (!a) return <EmptyState title="Not yet assessed" />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <RiskBadge level={a.level as RiskLevel} score={a.score} />
        <Link to={`/app/applications/${app.data.id}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-blue hover:underline">
          Open {app.data.reference} <ArrowUpRight className="size-3.5" />
        </Link>
      </div>
      <p className="text-sm text-slate-700">{a.explanation}</p>
      <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-amber-100">
        This is the detection engine's current view: a prioritisation aid, not a finding. {a.method} · {a.rules_version}
      </p>
      <SignalList signals={a.signals} />
    </div>
  );
}

function NotesPanel({ c, canWrite }: { c: CaseDetail; canWrite: boolean }) {
  const [body, setBody] = useState('');
  const add = useAddNote(c.id);
  const submit = () =>
    add.mutate({ body: body.trim() }, {
      onSuccess: () => {
        setBody('');
        toast.success('Note added', { description: 'Notes are append-only and audited.' });
      },
      onError: (err) => toast.error('Note not saved', { description: errorMessage(err) }),
    });
  return (
    <div className="space-y-4">
      {canWrite && (
        <div className="space-y-2">
          <label htmlFor="case-note" className="text-xs font-medium text-slate-700">Internal note</label>
          <Textarea id="case-note" value={body} maxLength={5000} onChange={(e) => setBody(e.target.value)} placeholder="What did you check? Who did you contact, and through which channel?" />
          <div className="flex justify-end">
            <Button size="sm" icon={<MessageSquarePlus className="size-4" />} loading={add.isPending} disabled={body.trim().length < 2} onClick={submit}>Add note</Button>
          </div>
        </div>
      )}
      {c.notes.length === 0 ? (
        <p className="text-sm text-slate-500">No notes yet.</p>
      ) : (
        <ul className="space-y-3">
          {[...c.notes].reverse().map((n) => (
            <li key={n.id} className="rounded-lg bg-slate-50 p-3.5">
              <p className="text-sm whitespace-pre-wrap text-slate-800">{n.body}</p>
              <p className="mt-1.5 text-[11px] text-slate-500">{n.author?.full_name ?? 'Unknown'} · {dateTime(n.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const timelineIcon: Record<string, ReactNode> = {
  'alert.raised': <Bell className="size-3.5" />,
  verification: <ShieldAlert className="size-3.5" />,
  'case.create': <FolderOpen className="size-3.5" />,
  'case.note_add': <MessageSquarePlus className="size-3.5" />,
  'case.evidence_add': <Paperclip className="size-3.5" />,
  'case.assign': <UserCheck className="size-3.5" />,
};

function Timeline({ c }: { c: CaseDetail }) {
  return (
    <div>
      <p className="mb-4 text-xs text-slate-500">Built from the tamper-evident audit trail, plus the detection events that led to this case.</p>
      <ol className="relative space-y-4 border-l border-slate-200 pl-6">
        {c.timeline.map((t, i) => {
          const decision = t.kind.startsWith('case.decision');
          const system = t.kind === 'alert.raised' || t.kind === 'verification';
          return (
            <li key={`${t.kind}-${i}`} className="relative">
              <span
                className={cn(
                  'absolute top-0.5 -left-[33px] flex size-5 items-center justify-center rounded-full ring-4 ring-white',
                  decision ? 'bg-navy-900 text-white' : system ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-600',
                )}
                aria-hidden
              >
                {decision ? <Scale className="size-3" /> : timelineIcon[t.kind] ?? <ScrollText className="size-3" />}
              </span>
              <p className={cn('text-sm', decision ? 'font-semibold text-slate-900' : 'font-medium text-slate-800')}>{t.title}</p>
              <p className="text-[11px] text-slate-500">{dateTime(t.at)} · {t.actor ?? 'system'}</p>
              {t.detail && <p className="mt-1 text-sm text-slate-600">{t.detail}</p>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function FactsCard({ c }: { c: CaseDetail }) {
  return (
    <Card>
      <CardHeader title="Case facts" icon={<FileText className="size-4" />} />
      <CardBody>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          {c.application && (
            <Fact label="Application" wide>
              <Link to={`/app/applications/${c.application.id}`} className="font-medium text-brand-blue hover:underline">{c.application.reference}</Link>
              <span className="ml-2 font-mono text-xs text-slate-500">{c.application.student_ref} · {c.application.masked_name}</span>
            </Fact>
          )}
          <Fact label="Risk at opening">{c.risk_score_at_open != null ? Math.round(c.risk_score_at_open) : '—'}</Fact>
          <Fact label="Current risk">{c.application ? <RiskBadge level={c.application.risk_level as RiskLevel | null} score={c.application.risk_score} /> : '—'}</Fact>
          <Fact label="Assigned to">{c.assigned_to?.full_name ?? <span className="text-amber-700">Unassigned</span>}</Fact>
          <Fact label="Due">{c.due_at ? <span className={c.overdue ? 'font-semibold text-red-700' : undefined}>{date(c.due_at)}</span> : '—'}</Fact>
          <Fact label="Review status">{c.application ? label(c.application.review_status) : '—'}</Fact>
          <Fact label="Last update">{dateTime(c.updated_at)}</Fact>
        </dl>
      </CardBody>
    </Card>
  );
}

function DecisionsCard({ c }: { c: CaseDetail }) {
  return (
    <Card>
      <CardHeader title="Decisions" description="Who decided, when, and why" icon={<Scale className="size-4" />} />
      <CardBody>
        {c.decisions.length === 0 ? (
          <p className="text-sm text-slate-500">No decision recorded yet. The case reflects suspicious activity only.</p>
        ) : (
          <ol className="space-y-3">
            {[...c.decisions].reverse().map((d) => (
              <li key={d.id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-semibold text-slate-900">{label(d.decision)}</span>
                  {d.outcome && <Badge tone="navy">{OUTCOMES[d.outcome as keyof typeof OUTCOMES]?.label ?? label(d.outcome)}</Badge>}
                  <Badge tone={findingMeta[d.finding]?.tone ?? 'neutral'}>{findingMeta[d.finding]?.label ?? d.finding}</Badge>
                </div>
                <p className="mt-1.5 text-sm text-slate-700">{d.justification}</p>
                <p className="mt-1.5 text-[11px] text-slate-500">{d.decided_by?.full_name ?? 'Unknown'} · {dateTime(d.decided_at)}</p>
              </li>
            ))}
          </ol>
        )}
      </CardBody>
    </Card>
  );
}

function AlertsCard({ c }: { c: CaseDetail }) {
  if (c.alerts.length === 0) return null;
  return (
    <Card>
      <CardHeader title="Linked alerts" icon={<Bell className="size-4" />} />
      <CardBody>
        <ul className="space-y-2">
          {c.alerts.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-2 text-sm">
              <Link to={`/app/alerts?selected=${a.id}&tab=all`} className="min-w-0 truncate text-slate-800 hover:text-brand-blue">{a.reference} · {a.title}</Link>
              <StatusBadge value={a.status} map={alertStatusTone} />
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}

function Fact({ label: name, children, wide }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? 'col-span-2' : undefined}>
      <dt className="text-xs text-slate-500">{name}</dt>
      <dd className="mt-0.5 text-slate-800">{children}</dd>
    </div>
  );
}
