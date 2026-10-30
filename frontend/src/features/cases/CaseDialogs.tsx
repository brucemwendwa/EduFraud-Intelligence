import { useQuery } from '@tanstack/react-query';
import { Paperclip, UserCheck } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import type { ApplicationDetail, CaseDetail, CaseEvidenceCreate } from '@/api/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { Field, Input, Select, Textarea } from '@/components/ui/Field';
import { Spinner } from '@/components/ui/Spinner';
import { api, errorMessage } from '@/lib/api';
import { cn } from '@/lib/cn';
import { date, label, money } from '@/lib/format';
import { useAddEvidence, useAssignCase, useAssignees } from './api';

interface DialogProps {
  c: CaseDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AssignDialog({ c, open, onOpenChange }: DialogProps) {
  const assignees = useAssignees(open);
  const [choice, setChoice] = useState(c.assigned_to?.id ?? '');
  const [note, setNote] = useState('');
  const assign = useAssignCase(c.id);

  const submit = () =>
    assign.mutate(
      { assigned_to_id: choice || null, note: note.trim() || undefined },
      {
        onSuccess: (res) => {
          toast.success(res.assigned_to ? `Assigned to ${res.assigned_to.full_name}` : 'Case unassigned', { description: res.reference });
          setNote('');
          onOpenChange(false);
        },
        onError: (err) => toast.error('Assignment failed', { description: errorMessage(err) }),
      },
    );

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={`Assign ${c.reference}`}
      description="Only active staff at this institution with case-update access can be assigned. The assignee is notified."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={assign.isPending} icon={<UserCheck className="size-4" />} disabled={choice === (c.assigned_to?.id ?? '')}>
            Save assignment
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Investigator">
          {(id) =>
            assignees.isLoading ? (
              <Spinner />
            ) : (
              <Select id={id} value={choice} onChange={(e) => setChoice(e.target.value)}>
                <option value="">Unassigned</option>
                {assignees.data?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.full_name}{a.title ? ` · ${a.title}` : ''} · {a.open_cases} open
                  </option>
                ))}
              </Select>
            )
          }
        </Field>
        <Field label="Handover note (optional)" hint="Stored in the audit trail.">
          {(id, d) => <Input id={id} aria-describedby={d} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />}
        </Field>
      </div>
    </Modal>
  );
}

interface Candidate {
  type: CaseEvidenceCreate['evidence_type'];
  id: string;
  title: string;
  detail: string;
}

function candidates(app: ApplicationDetail): Candidate[] {
  const out: Candidate[] = [{ type: 'application', id: app.id, title: `Application ${app.reference}`, detail: app.program }];
  if (app.assessment) {
    out.push({ type: 'risk_assessment', id: app.assessment.id, title: `Risk assessment ${Math.round(app.assessment.score)}/100`, detail: app.assessment.explanation });
  }
  for (const a of app.alerts) out.push({ type: 'alert', id: a.id, title: `Alert ${a.reference}`, detail: a.title });
  for (const v of app.verifications) out.push({ type: 'verification', id: v.id, title: `Verification ${v.reference} (${v.status})`, detail: `${label(v.trigger)} · ${label(v.method)}` });
  for (const d of app.disbursements) out.push({ type: 'disbursement', id: d.id, title: `Disbursement ${d.reference} · ${money(d.amount, true)}`, detail: `${label(d.fund_type)} · ${date(d.disbursed_at)}` });
  return out;
}

/** Attach a related record (snapshotted by the server) or a free-text document note. */
export function AddEvidenceDialog({ c, open, onOpenChange }: DialogProps) {
  const [mode, setMode] = useState<'record' | 'note'>('record');
  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  const add = useAddEvidence(c.id);
  const app = useQuery({
    queryKey: ['applications', 'detail', c.application_id],
    queryFn: async () => (await api.get<ApplicationDetail>(`/applications/${c.application_id}`)).data,
    enabled: open && Boolean(c.application_id),
  });
  const attached = new Set(c.evidence.map((e) => `${e.evidence_type}:${e.ref_id}`));
  const available = app.data ? candidates(app.data).filter((x) => !attached.has(`${x.type}:${x.id}`)) : [];

  const attach = (body: CaseEvidenceCreate) =>
    add.mutate(body, {
      onSuccess: () => {
        toast.success('Evidence attached', { description: 'Snapshot stored with the case.' });
        setTitle('');
        setSummary('');
        if (mode === 'note') onOpenChange(false);
      },
      onError: (err) => toast.error('Could not attach evidence', { description: errorMessage(err) }),
    });

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={`Add evidence · ${c.reference}`}
      description="Referenced records are copied from the source by the server, so the evidence trail cannot be edited by hand."
      footer={<Button variant="secondary" onClick={() => onOpenChange(false)}>Done</Button>}
    >
      <div className="mb-4 inline-flex rounded-lg bg-slate-100 p-1" role="tablist">
        {(['record', 'note'] as const).map((m) => (
          <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
            className={cn('rounded-md px-3 py-1.5 text-sm font-medium', mode === m ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600')}>
            {m === 'record' ? 'Related record' : 'Document note'}
          </button>
        ))}
      </div>
      {mode === 'record' ? (
        app.isLoading ? (
          <Spinner />
        ) : available.length === 0 ? (
          <p className="text-sm text-slate-500">Every related record is already attached.</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {available.map((x) => (
              <li key={`${x.type}:${x.id}`} className="flex items-center gap-3 px-3.5 py-2.5">
                <Badge tone="navy">{label(x.type)}</Badge>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900">{x.title}</p>
                  <p className="truncate text-xs text-slate-500">{x.detail}</p>
                </div>
                <Button size="sm" variant="secondary" icon={<Paperclip className="size-3.5" />} loading={add.isPending && add.variables?.ref_id === x.id}
                  onClick={() => attach({ evidence_type: x.type, ref_id: x.id })}>
                  Attach
                </Button>
              </li>
            ))}
          </ul>
        )
      ) : (
        <div className="space-y-4">
          <Field label="Title">{(id) => <Input id={id} value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Bank confirmation letter" />}</Field>
          <Field label="Summary" hint="Describe the document and where the original is held.">
            {(id, d) => <Textarea id={id} aria-describedby={d} value={summary} maxLength={5000} onChange={(e) => setSummary(e.target.value)} />}
          </Field>
          <div className="flex justify-end">
            <Button loading={add.isPending} disabled={title.trim().length < 2 || summary.trim().length < 2}
              onClick={() => attach({ evidence_type: 'document_note', title: title.trim(), summary: summary.trim() })}>
              Attach note
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
