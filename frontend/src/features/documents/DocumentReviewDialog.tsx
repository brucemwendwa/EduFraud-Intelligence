import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Field, Select, Textarea } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Dialog';
import { errorMessage } from '@/lib/api';
import { useReviewDocument } from './api';

export function DocumentReviewDialog({ open, onOpenChange, applicationId, documentId, filename }: { open: boolean; onOpenChange: (open: boolean) => void; applicationId: string; documentId: string; filename: string }) {
  const review = useReviewDocument(); const [decision, setDecision] = useState<'accepted' | 'rejected' | 'replacement_requested'>('accepted'); const [reason, setReason] = useState(''); const [error, setError] = useState<string | null>(null);
  const submit = async () => { const text = reason.trim(); if (text.length < 5 || text.length > 1000) return setError('Provide a reason between 5 and 1000 characters.'); setError(null); try { await review.mutateAsync({ applicationId, documentId, decision, reason: text }); toast.success('Document review recorded'); onOpenChange(false); } catch (err) { setError(errorMessage(err)); } };
  return <Modal open={open} onOpenChange={onOpenChange} title="Review document" description={`${filename} passed security scanning; record the evidence review separately.`} footer={<><Button variant="secondary" disabled={review.isPending} onClick={() => onOpenChange(false)}>Cancel</Button><Button loading={review.isPending} disabled={reason.trim().length < 5 || reason.trim().length > 1000} onClick={() => void submit()}>Record review</Button></>}><div className="space-y-4"><Field label="Decision">{(id, describedBy) => <Select id={id} aria-describedby={describedBy} value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)} disabled={review.isPending}><option value="accepted">Accept evidence</option><option value="rejected">Reject evidence</option><option value="replacement_requested">Request replacement</option></Select>}</Field><Field label="Reason" hint="5–1000 characters. Recorded in the audit log." error={error}>{(id, describedBy) => <Textarea id={id} aria-describedby={describedBy} value={reason} maxLength={1000} onChange={(event) => setReason(event.target.value)} disabled={review.isPending} autoFocus />}</Field></div></Modal>;
}
