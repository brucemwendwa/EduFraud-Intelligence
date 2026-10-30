import { FileSearch, FlaskConical, X } from 'lucide-react';
import { useNavigate } from 'react-router';
import { Badge, StatusBadge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Field';
import { SearchInput } from '@/components/ui/SearchInput';
import { PageHeader } from '@/components/ui/PageHeader';
import { RiskBadge, type RiskLevel } from '@/components/ui/Risk';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States';
import { Pagination, SortableTH, TD, TH, THead, TR, Table, type SortDir } from '@/components/ui/Table';
import { useAuth } from '@/lib/auth';
import { date, label, money } from '@/lib/format';
import {
  applicationStatusTone,
  isControlScenario,
  reviewStatusTone,
  scenarioLabels,
  verificationStatusTone,
} from '@/lib/status';
import { toParams, useSearchState } from '@/lib/useSearchState';
import { useApplications } from './api';

const DEFAULTS = {
  q: '',
  risk_level: '',
  status: '',
  review_status: '',
  verification_status: '',
  scenario: '',
  sort: 'risk_score',
  direction: 'desc',
  page: '1',
};

export default function ApplicationsPage() {
  const navigate = useNavigate();
  const { user, activeOrgId } = useAuth();
  const [filters, setFilters, reset] = useSearchState(DEFAULTS);
  const { data, isLoading, isFetching, error, refetch } = useApplications({ ...toParams(filters), page_size: '20' });
  const showInstitution = Boolean(user?.is_platform_admin && !activeOrgId);
  const filtered = Object.entries(filters).some(([k, v]) => !['sort', 'direction', 'page'].includes(k) && v);

  const onSort = (field: string) =>
    setFilters({
      sort: field,
      direction: filters.sort === field && filters.direction === 'desc' ? 'asc' : 'desc',
    });

  return (
    <>
      <PageHeader
        title="Applications"
        description="Financial aid applications with their current risk assessment. Scores are recommendations for human review, never automated decisions."
      />
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
          <div className="w-full sm:w-64">
            <SearchInput
              placeholder="Search FA- or STU- reference"
              label="Search applications"
              value={filters.q}
              onChange={(q) => setFilters({ q })}
            />
          </div>
          <FilterSelect label="Risk level" value={filters.risk_level} onChange={(v) => setFilters({ risk_level: v })}
            options={['critical', 'high', 'medium', 'low']} />
          <FilterSelect label="Status" value={filters.status} onChange={(v) => setFilters({ status: v })}
            options={['received', 'in_review', 'approved', 'on_hold', 'withdrawn']} />
          <FilterSelect label="Review" value={filters.review_status} onChange={(v) => setFilters({ review_status: v })}
            options={['unreviewed', 'in_review', 'cleared', 'escalated']} />
          <FilterSelect label="Verification" value={filters.verification_status}
            onChange={(v) => setFilters({ verification_status: v })}
            options={['not_required', 'pending', 'passed', 'failed', 'manual_review']} />
          <Select
            aria-label="Demo scenario"
            value={filters.scenario}
            onChange={(e) => setFilters({ scenario: e.target.value })}
            className="w-full sm:w-52"
          >
            <option value="">All records</option>
            <option value="any">Any demo scenario</option>
            {Object.entries(scenarioLabels).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </Select>
          {filtered && (
            <Button variant="ghost" size="sm" icon={<X className="size-3.5" />} onClick={reset}>
              Clear filters
            </Button>
          )}
        </div>

        {isLoading ? (
          <TableSkeleton rows={8} cols={7} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            icon={<FileSearch className="size-5" />}
            title="No applications match these filters"
            description="Try a different risk level or clear the filters to see every application in scope."
            action={filtered ? <Button variant="secondary" size="sm" onClick={reset}>Clear filters</Button> : undefined}
          />
        ) : (
          <div className={isFetching ? 'opacity-70 transition-opacity' : undefined}>
            <Table>
              <THead>
                <tr>
                  <SortableTH label="Application" field="reference" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Student</TH>
                  {showInstitution && <TH>Institution</TH>}
                  <SortableTH label="Submitted" field="submitted_at" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <SortableTH label="Requested" field="requested_amount" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} className="text-right" />
                  <TH>Status</TH>
                  <SortableTH label="Risk" field="risk_score" sort={filters.sort} dir={filters.direction as SortDir} onSort={onSort} />
                  <TH>Verification</TH>
                  <TH>Review</TH>
                </tr>
              </THead>
              <tbody>
                {data.items.map((row) => (
                  <TR key={row.id} onClick={() => navigate(`/app/applications/${row.id}`)}>
                    <TD>
                      <a
                        href={`/app/applications/${row.id}`}
                        onClick={(e) => {
                          e.preventDefault();
                          navigate(`/app/applications/${row.id}`);
                        }}
                        className="font-medium text-slate-900 hover:text-brand-blue"
                      >
                        {row.reference}
                      </a>
                      {row.scenario_key && (
                        <div className="mt-1">
                          <Badge tone={isControlScenario(row.scenario_key) ? 'success' : 'violet'} icon={<FlaskConical className="size-3" />}>
                            {scenarioLabels[row.scenario_key] ?? label(row.scenario_key)}
                          </Badge>
                        </div>
                      )}
                    </TD>
                    <TD>
                      <div className="font-mono text-xs text-slate-700">{row.student.student_ref}</div>
                      <div className="text-xs text-slate-500">{row.student.masked_name}</div>
                    </TD>
                    {showInstitution && <TD className="text-xs">{row.organization.name}</TD>}
                    <TD className="tabular whitespace-nowrap">{date(row.submitted_at)}</TD>
                    <TD className="tabular text-right">{money(row.requested_amount)}</TD>
                    <TD><StatusBadge value={row.status} map={applicationStatusTone} /></TD>
                    <TD>
                      <div className="flex items-center gap-1.5">
                        <RiskBadge level={row.risk_level as RiskLevel | null} score={row.risk_score} />
                        {row.open_alerts > 0 && (
                          <span className="tabular rounded-full bg-red-50 px-1.5 text-[11px] font-semibold text-red-700 ring-1 ring-red-100" title={`${row.open_alerts} open alert(s)`}>
                            {row.open_alerts}
                          </span>
                        )}
                      </div>
                    </TD>
                    <TD><StatusBadge value={row.verification_status} map={verificationStatusTone} /></TD>
                    <TD><StatusBadge value={row.review_status} map={reviewStatusTone} /></TD>
                  </TR>
                ))}
              </tbody>
            </Table>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setFilters({ page: String(p) })} />
          </div>
        )}
      </Card>
    </>
  );
}

function FilterSelect({ label: name, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <Select aria-label={name} value={value} onChange={(e) => onChange(e.target.value)} className="w-[calc(50%-0.25rem)] sm:w-40">
      <option value="">{name}: all</option>
      {options.map((o) => (
        <option key={o} value={o}>{label(o)}</option>
      ))}
    </Select>
  );
}
