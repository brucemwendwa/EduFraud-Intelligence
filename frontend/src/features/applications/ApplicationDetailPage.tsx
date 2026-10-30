import { ArrowUpRight, Building2, ClipboardCheck, FlaskConical, Link2, Network } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router';
import type { ApplicationDetail } from '@/api/types';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { CardSkeleton, EmptyState, ErrorState, Skeleton } from '@/components/ui/States';
import { TD, TH, THead, TR, Table } from '@/components/ui/Table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import { useAuth } from '@/lib/auth';
import { date, dateTime, label, money } from '@/lib/format';
import { P } from '@/lib/permissions';
import {
  applicationStatusTone,
  disbursementStatusTone,
  enrollmentStatusTone,
  isControlScenario,
  reviewStatusTone,
  scenarioLabels,
  verificationStatusTone,
} from '@/lib/status';
import { useApplication } from './api';
import { ReviewDialog } from './ReviewDialog';
import { RiskPanel } from './RiskPanel';
import { StudentIdentityCard } from './StudentIdentityCard';

export default function ApplicationDetailPage() {
  const { id = '' } = useParams();
  const { data, isLoading, error, refetch } = useApplication(id);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-72" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2"><CardSkeleton /></Card>
          <Card><CardSkeleton /></Card>
        </div>
      </div>
    );
  }
  if (error || !data) return <ErrorState title="Application unavailable" error={error} onRetry={() => refetch()} />;
  return <ApplicationView app={data} />;
}

function ApplicationView({ app }: { app: ApplicationDetail }) {
  const { can } = useAuth();
  const [reviewOpen, setReviewOpen] = useState(false);
  const relatedCount = app.related.reduce((n, g) => n + g.matches.length + g.other_institution_matches, 0);

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'Applications', to: '/app/applications' }, { label: app.reference }]}
        title={app.reference}
        description={`${app.organization.name} · Award year ${app.award_year} · Submitted ${dateTime(app.submitted_at)}`}
        meta={
          <>
            <StatusBadge value={app.status} map={applicationStatusTone} />
            <Badge tone={reviewStatusTone[app.review_status]}>Review: {label(app.review_status)}</Badge>
            <Badge tone={verificationStatusTone[app.verification_status]}>Verification: {label(app.verification_status)}</Badge>
            {app.scenario_key && (
              <Badge tone={isControlScenario(app.scenario_key) ? 'success' : 'violet'} icon={<FlaskConical className="size-3" />}>
                Demo scenario: {scenarioLabels[app.scenario_key] ?? label(app.scenario_key)}
              </Badge>
            )}
          </>
        }
        actions={
          can(P.applicationsReview) && (
            <Button variant="secondary" icon={<ClipboardCheck className="size-4" />} onClick={() => setReviewOpen(true)}>
              Record review
            </Button>
          )
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <RiskPanel app={app} />
          <Card>
            <Tabs defaultValue="related">
              <div className="px-5 pt-2">
                <TabsList>
                  <TabsTrigger value="related" count={relatedCount}>Related records</TabsTrigger>
                  <TabsTrigger value="disbursements" count={app.disbursements.length}>Disbursements</TabsTrigger>
                  <TabsTrigger value="enrollment" count={app.enrollments.length}>Enrollment</TabsTrigger>
                  <TabsTrigger value="verification" count={app.verifications.length}>Verification</TabsTrigger>
                  <TabsTrigger value="tokens">Identity tokens</TabsTrigger>
                </TabsList>
              </div>
              <TabsContent value="related" className="p-5"><RelatedRecords app={app} /></TabsContent>
              <TabsContent value="disbursements"><Disbursements app={app} /></TabsContent>
              <TabsContent value="enrollment"><Enrollment app={app} /></TabsContent>
              <TabsContent value="verification"><Verifications app={app} /></TabsContent>
              <TabsContent value="tokens"><IdentityTokens app={app} /></TabsContent>
            </Tabs>
          </Card>
        </div>

        <div className="space-y-6">
          <StudentIdentityCard student={app.student_detail} />
          <Card>
            <CardHeader title="Application facts" icon={<Building2 className="size-4" />} />
            <CardBody>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                <Fact label="Program" wide>{app.program}</Fact>
                <Fact label="Requested">{money(app.requested_amount)}</Fact>
                <Fact label="Student Aid Index">{app.student_aid_index.toLocaleString()}</Fact>
                <Fact label="Dependency">{label(app.dependency_status)}</Fact>
                <Fact label="Enrollment">{label(app.enrollment_intensity)}</Fact>
                <Fact label="Channel">{label(app.submission_channel)}</Fact>
                <Fact label="Device token"><code className="text-xs">{app.device_handle ?? '—'}</code></Fact>
              </dl>
            </CardBody>
          </Card>
        </div>
      </div>
      <ReviewDialog applicationId={app.id} reference={app.reference} open={reviewOpen} onOpenChange={setReviewOpen} />
    </>
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

function RelatedRecords({ app }: { app: ApplicationDetail }) {
  const { can } = useAuth();
  if (app.related.length === 0) {
    return (
      <EmptyState
        icon={<Link2 className="size-5" />}
        title="No shared attributes"
        description="This application shares no identity token, device, network or payment destination with any other record."
      />
    );
  }
  return (
    <div className="space-y-4">
      {can(P.networkRead) && (
        <div className="flex justify-end">
          <Link to={`/app/network?focus=${app.id}`} className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-blue hover:underline">
            <Network className="size-4" /> Explore in fraud network
          </Link>
        </div>
      )}
      {app.related.map((group) => (
        <div key={`${group.kind}-${group.handle}`} className="rounded-lg border border-slate-200">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/60 px-4 py-2.5">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-900">{group.label}</span>
              <code className="rounded bg-white px-1.5 py-0.5 text-[11px] text-slate-600 ring-1 ring-slate-200">{group.handle}</code>
            </div>
            <span className="text-xs text-slate-500">
              {group.matches.length} in your scope
              {group.other_institution_matches > 0 && (
                <> · <span className="font-medium text-amber-700">{group.other_institution_matches} at other institutions</span></>
              )}
            </span>
          </div>
          {group.matches.length > 0 ? (
            <ul className="divide-y divide-slate-100">
              {group.matches.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <Link to={`/app/applications/${m.id}`} className="font-medium text-slate-800 hover:text-brand-blue">
                    {m.reference}
                    <ArrowUpRight className="ml-0.5 inline size-3.5" aria-hidden />
                  </Link>
                  <span className="hidden font-mono text-xs text-slate-500 sm:inline">{m.student_ref}</span>
                  <span className="hidden truncate text-xs text-slate-500 md:inline">{m.organization_name}</span>
                  <RiskBadge level={m.risk_level as RiskLevel | null} score={m.risk_score} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-3 text-xs text-slate-500">
              Matches exist only at other institutions. Their details are not shared across institutions.
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function Disbursements({ app }: { app: ApplicationDetail }) {
  if (app.disbursements.length === 0) return <EmptyState title="No disbursements" description="No funds have been scheduled for this student." />;
  return (
    <Table>
      <THead>
        <tr><TH>Reference</TH><TH>Fund</TH><TH className="text-right">Amount</TH><TH>Date</TH><TH>Destination</TH><TH>Status</TH><TH>Risk</TH></tr>
      </THead>
      <tbody>
        {app.disbursements.map((d) => (
          <TR key={d.id}>
            <TD className="font-medium text-slate-900">
              <Link to={`/app/disbursements?q=${d.reference}`} className="hover:text-brand-blue">{d.reference}</Link>
            </TD>
            <TD>{label(d.fund_type)}</TD>
            <TD className="tabular text-right">{money(d.amount, true)}</TD>
            <TD className="tabular whitespace-nowrap">{date(d.disbursed_at)}</TD>
            <TD>
              <code className="text-xs">{d.destination.handle}</code>
              {d.destination_changed_at && <div className="text-[11px] text-amber-700">Changed {date(d.destination_changed_at)}</div>}
            </TD>
            <TD><StatusBadge value={d.status} map={disbursementStatusTone} /></TD>
            <TD>{d.risk_score != null ? <RiskBadge level={levelOf(d.risk_score)} score={d.risk_score} /> : '—'}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

function levelOf(score: number): RiskLevel {
  return score >= 80 ? 'critical' : score >= 60 ? 'high' : score >= 30 ? 'medium' : 'low';
}

function Enrollment({ app }: { app: ApplicationDetail }) {
  if (app.enrollments.length === 0) return <EmptyState title="No enrollment records" />;
  return (
    <Table>
      <THead>
        <tr><TH>Term</TH><TH>Program</TH><TH>Credits</TH><TH>Modality</TH><TH>Status</TH><TH>Last attendance</TH></tr>
      </THead>
      <tbody>
        {app.enrollments.map((e) => (
          <TR key={e.id}>
            <TD className="font-medium text-slate-900">{e.term}</TD>
            <TD>{e.program}</TD>
            <TD className="tabular">{e.credit_hours}</TD>
            <TD>{label(e.modality)}</TD>
            <TD><StatusBadge value={e.status} map={enrollmentStatusTone} /></TD>
            <TD className="tabular">{e.last_attendance_at ? date(e.last_attendance_at) : <span className="text-red-700">None recorded</span>}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

function Verifications({ app }: { app: ApplicationDetail }) {
  if (app.verifications.length === 0) return <EmptyState title="No verification attempts" description="No identity verification has been performed for this student." />;
  return (
    <Table>
      <THead>
        <tr><TH>Reference</TH><TH>Trigger</TH><TH>Method</TH><TH>Face match</TH><TH>Liveness</TH><TH>Attack detection</TH><TH>Result</TH><TH>When</TH></tr>
      </THead>
      <tbody>
        {app.verifications.map((v) => (
          <TR key={v.id}>
            <TD className="font-medium text-slate-900">{v.reference}</TD>
            <TD>{label(v.trigger)}</TD>
            <TD>
              {label(v.method)}
              {v.provider_mode === 'simulation' && <Badge tone="blue" className="ml-1.5">Simulated</Badge>}
            </TD>
            <TD className="tabular">{v.face_match_score != null ? v.face_match_score.toFixed(2) : '—'}</TD>
            <TD>{label(v.liveness_result)}</TD>
            <TD>{v.pad_attack_type ? <span className="text-red-700">{label(v.pad_attack_type)}</span> : label(v.pad_result)}</TD>
            <TD><StatusBadge value={v.status} map={verificationStatusTone} /></TD>
            <TD className="tabular whitespace-nowrap">{dateTime(v.completed_at ?? v.created_at)}</TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

function IdentityTokens({ app }: { app: ApplicationDetail }) {
  return (
    <div>
      <p className="px-5 pt-4 text-xs text-slate-500">
        Raw identifiers are never stored. Each attribute is a keyed HMAC token, so matching works without exposing the
        underlying value.
      </p>
      <Table>
        <THead>
          <tr><TH>Attribute</TH><TH>Token</TH><TH>Other records in scope</TH><TH>Other institutions</TH></tr>
        </THead>
        <tbody>
          {app.student_detail.identity_tokens.map((t) => (
            <TR key={t.token_type}>
              <TD className="font-medium text-slate-900">{t.token_type === 'ssn' ? 'SSN' : t.token_type === 'dob' ? 'Date of birth' : label(t.token_type)}</TD>
              <TD><code className="text-xs">{t.handle}</code></TD>
              <TD className="tabular">{t.shared_in_scope > 0 ? <span className="font-medium text-amber-700">{t.shared_in_scope}</span> : 0}</TD>
              <TD className="tabular">{t.shared_other_institutions > 0 ? <span className="font-medium text-amber-700">{t.shared_other_institutions}</span> : 0}</TD>
            </TR>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
