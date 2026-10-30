import { useState } from 'react';
import { toast } from 'sonner';
import type { ReviewUpdate } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { Field, Select, Textarea } from '@/components/ui/Field';
import { errorMessage } from '@/lib/api';
import { useReviewApplication } from './api';

interface Props {
  applicationId: string;
  reference: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** A human review decision. EduShield never changes an application's status on its own. */
export function ReviewDialog({ applicationId, reference, open, onOpenChange }: Props) {
  const [reviewStatus, setReviewStatus] = useState<ReviewUpdate['review_status']>('in_review');
  const [appStatus, setAppStatus] = useState<string>('');
  const [note, setNote] = useState('');
  const review = useReviewApplication(applicationId);
  const valid = note.trim().length >= 5;

  const submit = () =>
    review.mutate(
      {
        review_status: reviewStatus,
        application_status: (appStatus || null) as ReviewUpdate['application_status'],
        note: note.trim(),
      },
      {
        onSuccess: () => {
          toast.success('Review recorded', { description: `${reference} · decision saved to the audit trail` });
          setNote('');
          onOpenChange(false);
        },
        onError: (err) => toast.error('Review not saved', { description: errorMessage(err) }),
      },
    );

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={`Record review · ${reference}`}
      description="Your decision and note are stored in the audit trail."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} loading={review.isPending} disabled={!valid}>Save decision</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Review outcome">
          {(id) => (
            <Select id={id} value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value as ReviewUpdate['review_status'])}>
              <option value="in_review">In review: gathering information</option>
              <option value="cleared">Cleared: no concerns after review</option>
              <option value="escalated">Escalated: refer to investigations</option>
            </Select>
          )}
        </Field>
        <Field label="Application status (optional)" hint="Leave unchanged unless your review requires it.">
          {(id, d) => (
            <Select id={id} aria-describedby={d} value={appStatus} onChange={(e) => setAppStatus(e.target.value)}>
              <option value="">Keep current status</option>
              <option value="in_review">In review</option>
              <option value="on_hold">On hold pending verification</option>
              <option value="approved">Approved</option>
            </Select>
          )}
        </Field>
        <Field label="Review note" hint="Minimum 5 characters. Describe what you checked.">
          {(id, d) => (
            <Textarea id={id} aria-describedby={d} value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
          )}
        </Field>
      </div>
    </Modal>
  );
}
