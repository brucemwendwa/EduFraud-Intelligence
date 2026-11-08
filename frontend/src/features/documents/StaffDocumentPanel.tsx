import { useState } from 'react';
import { Download, FileText } from 'lucide-react';
import type { ApplicationDocument } from '@/api/types';
import { Badge, StatusBadge, humanize, type Tone } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { errorMessage } from '@/lib/api';
import { DocumentReviewDialog } from './DocumentReviewDialog';
import { requestStaffDocumentDownload, useStaffDocuments } from './api';

const scanTone: Record<string, Tone> = { pending_scan: 'warning', scanning: 'blue', available: 'success', rejected: 'critical', failed: 'critical', superseded: 'neutral' };
const reviewTone: Record<string, Tone> = { pending: 'neutral', accepted: 'success', rejected: 'critical', replacement_requested: 'warning' };
const size = (n: number) => n < 1048576 ? `${Math.max(1, Math.ceil(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`;
const statusMessage = (status: string) => ({ pending_scan: 'Waiting for security checks.', scanning: 'Security checks in progress.', rejected: 'Rejected by security scanning.', failed: 'Security processing failed.', superseded: 'Replaced by a newer document.' }[status] ?? 'Security checks passed. Staff review is separate.');
function openDownload(url: string) { const link = document.createElement('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; document.body.append(link); link.click(); link.remove(); }

export function StaffDocumentPanel({ applicationId, canReview }: { applicationId: string; canReview: boolean }) {
  const documents = useStaffDocuments(applicationId); const [reviewing, setReviewing] = useState<ApplicationDocument | null>(null); const [downloadError, setDownloadError] = useState<string | null>(null); const [downloading, setDownloading] = useState<string | null>(null);
  const download = async (doc: ApplicationDocument) => { setDownloadError(null); setDownloading(doc.id); try { openDownload((await requestStaffDocumentDownload(doc.id)).url); } catch (err) { setDownloadError(errorMessage(err)); } finally { setDownloading(null); } };
  return <Card><CardHeader title="Evidence" description="Security scanning and staff evidence review are separate decisions." /><CardBody>{documents.isLoading && <p role="status" className="py-6 text-sm text-slate-500">Loading documents</p>}{documents.isError && <ErrorState title="Could not load documents" error={documents.error} onRetry={() => void documents.refetch()} />}{documents.data?.length === 0 && <EmptyState title="No evidence documents" description="The student has not attached supporting documents." />}{documents.data && documents.data.length > 0 && <ul>{documents.data.map((doc) => { const available = doc.status === 'available'; return <li key={doc.id} className="border-b border-slate-100 py-4 last:border-0"><div className="flex flex-wrap justify-between gap-3"><div><p className="flex items-center gap-2 text-sm font-medium"><FileText className="size-4" />{doc.original_filename}</p><p className="mt-1 text-xs text-slate-500">{humanize(doc.category)} · {size(doc.size_bytes)} · Uploaded {new Date(doc.created_at).toLocaleDateString()}</p></div><div className="flex gap-2"><StatusBadge value={doc.status} map={scanTone} /><Badge tone={reviewTone[doc.review_status] ?? 'neutral'}>Review: {humanize(doc.review_status)}</Badge></div></div><p className="mt-2 text-xs text-slate-600">{statusMessage(doc.status)}</p><div className="mt-3 flex gap-2"><Button size="sm" variant="secondary" icon={<Download className="size-3.5" />} disabled={!available} loading={downloading === doc.id} onClick={() => void download(doc)}>Download</Button>{canReview && available && <Button size="sm" variant="secondary" onClick={() => setReviewing(doc)}>Review evidence</Button>}</div></li>; })}</ul>}{downloadError && <p role="alert" className="mt-3 text-sm text-red-700">{downloadError}</p>}</CardBody>{reviewing && <DocumentReviewDialog open onOpenChange={(open) => !open && setReviewing(null)} applicationId={applicationId} documentId={reviewing.id} filename={reviewing.original_filename} />}</Card>;
}
