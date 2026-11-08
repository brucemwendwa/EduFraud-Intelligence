import { useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { Download, FileText, RefreshCw, ShieldCheck, Upload } from 'lucide-react';
import { toast } from 'sonner';
import type { ApplicationDocument } from '@/api/types';
import { Badge, StatusBadge, type Tone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Field, Input, Select } from '@/components/ui/Field';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { errorMessage, ApiError } from '@/lib/api';
import { humanize } from '@/components/ui/Badge';
import {
  requestStudentDocumentDownload,
  useStudentDocumentReplacement,
  useStudentDocuments,
  useStudentDocumentUpload,
} from './api';

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ACCEPTED_TYPES = new Set(['application/pdf', 'image/jpeg', 'image/png']);
const CATEGORIES = [
  ['government_id', 'Government ID'],
  ['admission_proof', 'Admission proof'],
  ['academic_record', 'Academic record'],
  ['income_evidence', 'Income evidence'],
  ['guardian_sponsor', 'Guardian or sponsor statement'],
  ['other', 'Other supporting document'],
] as const;
type DocumentCategory = (typeof CATEGORIES)[number][0];
const isDocumentCategory = (value: string): value is DocumentCategory =>
  CATEGORIES.some(([category]) => category === value);

const scanTone: Record<string, Tone> = {
  pending_scan: 'warning', scanning: 'blue', available: 'success', rejected: 'critical', superseded: 'neutral', failed: 'critical',
};
const reviewTone: Record<string, Tone> = {
  pending: 'neutral', accepted: 'success', rejected: 'critical', replacement_requested: 'warning',
};

interface StudentDocumentPanelProps {
  applicationId: string;
  isEditable: boolean;
}

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function scanMessage(status: string) {
  if (status === 'pending_scan') return 'Quarantined until security checks begin.';
  if (status === 'scanning') return 'Security checks are in progress.';
  if (status === 'available') return 'Security checks passed. Staff review is separate.';
  if (status === 'rejected') return 'Security checks rejected this document.';
  if (status === 'failed') return 'Security checks could not be completed. Please contact support.';
  if (status === 'superseded') return 'A verified replacement is now on record.';
  return 'Document status is being updated.';
}

function canReplace(document: ApplicationDocument, isEditable: boolean) {
  return document.status !== 'superseded' && (isEditable || document.review_status === 'replacement_requested');
}

function validateFile(file: File | undefined): string | null {
  if (!file) return 'Choose a PDF, JPEG, or PNG document.';
  if (!ACCEPTED_TYPES.has(file.type)) return 'Choose a PDF, JPEG, or PNG document.';
  if (file.size > MAX_UPLOAD_BYTES) return 'Files must be 10 MB or smaller.';
  return null;
}

function downloadUrl(url: string) {
  const link = document.createElement('a');
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  document.body.append(link);
  link.click();
  link.remove();
}

function ReplacementForm({ document, applicationId, onClose }: { document: ApplicationDocument; applicationId: string; onClose: () => void }) {
  const replacement = useStudentDocumentReplacement();
  const [file, setFile] = useState<File>();
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validation = validateFile(file);
    if (validation) return setError(validation);
    setError(null);
    try {
      await replacement.mutateAsync({
        applicationId,
        documentId: document.id,
        category: isDocumentCategory(document.category) ? document.category : 'other',
        file: file!,
      });
      toast.success('Replacement uploaded for security checks');
      if (fileRef.current) fileRef.current.value = '';
      setFile(undefined);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409
        ? 'A replacement is already awaiting verification. Wait for it to finish before trying again.'
        : errorMessage(err));
    }
  };

  return <form className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3" onSubmit={submit}>
    <p className="text-xs text-amber-900">The original remains on record until this replacement passes security checks.</p>
    <Field label={`Replacement file for ${document.original_filename}`} error={error} className="mt-3">
      {(id, describedBy) => <Input ref={fileRef} id={id} aria-describedby={describedBy} type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0])} disabled={replacement.isPending} />}
    </Field>
    <div className="mt-3 flex gap-2"><Button type="submit" size="sm" loading={replacement.isPending}>Upload replacement</Button><Button type="button" size="sm" variant="secondary" disabled={replacement.isPending} onClick={onClose}>Cancel</Button></div>
  </form>;
}

function DocumentRow({ document, applicationId, isEditable }: { document: ApplicationDocument; applicationId: string; isEditable: boolean }) {
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const available = document.status === 'available';

  const download = async () => {
    setDownloadError(null); setDownloading(true);
    try { downloadUrl((await requestStudentDocumentDownload(document.id)).url); }
    catch (err) { setDownloadError(errorMessage(err)); }
    finally { setDownloading(false); }
  };

  return <li className="border-b border-slate-100 py-4 last:border-0">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0"><div className="flex items-center gap-2"><FileText className="size-4 shrink-0 text-navy-600" aria-hidden /><p className="truncate text-sm font-medium text-slate-900">{document.original_filename}</p></div>
        <p className="mt-1 text-xs text-slate-500">{humanize(document.category)} · {formatSize(document.size_bytes)} · Uploaded {new Date(document.created_at).toLocaleDateString()}</p></div>
      <div className="flex flex-wrap items-center gap-2"><StatusBadge value={document.status} map={scanTone} /><Badge tone={reviewTone[document.review_status] ?? 'neutral'}>Review: {humanize(document.review_status)}</Badge></div>
    </div>
    <p className="mt-2 text-xs text-slate-600">{scanMessage(document.status)}</p>
    {document.review_reason && <p className="mt-1 text-xs text-slate-600">Staff note: {document.review_reason}</p>}
    {!available && <p className="mt-1 text-xs text-slate-500">Downloads are available only after security checks pass.</p>}
    <div className="mt-3 flex flex-wrap gap-2"><Button size="sm" variant="secondary" icon={<Download className="size-3.5" />} loading={downloading} disabled={!available} title={available ? 'Request a short-lived download link' : 'Available after security checks pass'} onClick={() => void download()}>Download</Button>
      {canReplace(document, isEditable) && <Button size="sm" variant="secondary" icon={<RefreshCw className="size-3.5" />} onClick={() => setReplaceOpen((open) => !open)}>Replace document</Button>}</div>
    {downloadError && <p role="alert" className="mt-2 text-xs text-red-700">{downloadError}</p>}
    {replaceOpen && <ReplacementForm document={document} applicationId={applicationId} onClose={() => setReplaceOpen(false)} />}
  </li>;
}

export function StudentDocumentPanel({ applicationId, isEditable }: StudentDocumentPanelProps) {
  const documents = useStudentDocuments(applicationId);
  const upload = useStudentDocumentUpload();
  const [category, setCategory] = useState<DocumentCategory>('income_evidence');
  const [file, setFile] = useState<File>();
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validation = validateFile(file);
    if (validation) return setError(validation);
    setError(null);
    try {
      await upload.mutateAsync({ applicationId, category, file: file! });
      toast.success('Document uploaded for security checks');
      if (fileRef.current) fileRef.current.value = '';
      setFile(undefined);
    } catch (err) { setError(errorMessage(err)); }
  };

  return <Card className="mt-6"><CardHeader title="Supporting documents" description="Files are quarantined until security checks pass." icon={<ShieldCheck className="size-5" />} />
    <CardBody>
      {isEditable && <form className="grid gap-3 rounded-lg bg-slate-50 p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto]" onSubmit={submit}>
        <Field label="Document category">{(id, describedBy) => <Select id={id} aria-describedby={describedBy} value={category} onChange={(event) => setCategory(CATEGORIES.find(([value]) => value === event.target.value)?.[0] ?? 'other')} disabled={upload.isPending}>{CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>}</Field>
        <Field label="Choose a file" hint="PDF, JPEG, or PNG · maximum 10 MB" error={error}>{(id, describedBy) => <Input ref={fileRef} id={id} aria-describedby={describedBy} type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0])} disabled={upload.isPending} />}</Field>
        <div className="self-end"><Button type="submit" icon={<Upload className="size-3.5" />} loading={upload.isPending}>Upload</Button></div>
      </form>}
      {!isEditable && <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">New uploads are available only while this application is editable. You can still replace a document if staff explicitly requested one.</p>}
      {documents.isLoading && <div role="status" className="flex items-center gap-2 py-8 text-sm text-slate-500"><RefreshCw className="size-4 animate-spin" /> Loading documents</div>}
      {documents.isError && <ErrorState title="Could not load documents" error={documents.error} onRetry={() => void documents.refetch()} />}
      {documents.data && documents.data.length === 0 && <EmptyState title="No supporting documents yet" description={isEditable ? 'Upload the documents requested for this application.' : 'No documents have been attached to this application.'} />}
      {documents.data && documents.data.length > 0 && <ul className="mt-3">{documents.data.map((document) => <DocumentRow key={document.id} document={document} applicationId={applicationId} isEditable={isEditable} />)}</ul>}
    </CardBody>
  </Card>;
}
