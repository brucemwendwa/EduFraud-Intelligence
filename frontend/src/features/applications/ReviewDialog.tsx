import { useState } from 'react';
import { toast } from 'sonner';
import type { ReviewUpdate } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { Field, Select, Textarea } from '@/components/ui/Field';
import { errorMessage } from '@/lib/api';
import { label } from '@/lib/format';
import { useReviewApplication } from './api';

interface Props {
  applicationId: string;
  reference: string;
  currentStatus: string;
  /** Next statuses the API will accept for this application. */
  allowedStatusChanges: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const STATUS_LABELS: Record<string, string> = {
  in_review: 'In review',
  additional_information_required: 'Request additional information',
  on_hold: 'On hold pending verification',
  approved: 'Approve application',
  rejected: 'Reject application',
};
const FINAL = new Set(['approved', 'rejected']);
const MESSAGE_REQUIRED = new Set(['additional_information_required', 'rejected']);
const MESSAGE_ALLOWED = new Set([...MESSAGE_REQUIRED, 'approved']);

/** A human review decision. EduShield never changes an application's status on its own. */
export function ReviewDialog({ applicationId, reference, currentStatus, allowedStatusChanges, open, onOpenChange }: Props) {
  const [reviewStatus, setReviewStatus] = useState<ReviewUpdate['review_status']>('in_review');
  const [appStatus, setAppStatus] = useState('');
  const [note, setNote] = useState('');
  const [studentMessage, setStudentMessage] = useState('');
  const review = useReviewApplication(applicationId);

  const showMessage = MESSAGE_ALLOWED.has(appStatus);
  const messageRequired = MESSAGE_REQUIRED.has(appStatus);
  const message = showMessage ? studentMessage.trim() : '';
  const valid = note.trim().length >= 5 && (message.length >= 5 || (!messageRequired && message.length === 0));

  const close = (next: boolean) => {
    if (!next) {
      setAppStatus('');
      setNote('');
      setStudentMessage('');
      setReviewStatus('in_review');
    }
    onOpenChange(next);
  };

  const submit = () =>
    review.mutate(
      {
        review_status: reviewStatus,
        application_status: (appStatus || null) as ReviewUpdate['application_status'],
        note: note.trim(),
        student_message: message || null,
      },
      {
        onSuccess: () => {
          toast.success('Review recorded', { description: `${reference} · decision saved to the audit trail` });
          close(false);
        },
        onError: (err) => toast.error('Review not saved', { description: errorMessage(err) }),
      },
    );

  return (
    <Modal
      open={open}
      onOpenChange={close}
      title={`Record review · ${reference}`}
      description="Your decision and note are stored in the audit trail. Risk scores are advisory: this decision is yours."
      footer={
        <>
          <Button variant="secondary" onClick={() => close(false)}>Cancel</Button>
          <Button onClick={submit} loading={review.isPending} disabled={!valid}>Save decision</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Application decision" hint={`Current status: ${label(currentStatus)}`}>
          {(id, d) => (
            <Select id={id} aria-describedby={d} value={appStatus} onChange={(e) => setAppStatus(e.target.value)}>
              <option value="">Keep current status</option>
              {allowedStatusChanges.map((status) => (
                <option key={status} value={status}>{STATUS_LABELS[status] ?? label(status)}</option>
              ))}
            </Select>
          )}
        </Field>
        {FINAL.has(appStatus) && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-100">
            This is a final decision on the application and cannot be changed afterwards.
          </p>
        )}
        <Field label="Review outcome">
          {(id) => (
            <Select id={id} value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value as ReviewUpdate['review_status'])}>
              <option value="in_review">In review: gathering information</option>
              <option value="cleared">Cleared: no concerns after review</option>
              <option value="escalated">Escalated: refer to investigations</option>
            </Select>
          )}
        </Field>
        <Field label="Internal review note" hint="Minimum 5 characters. Staff only: never shown to the student.">
          {(id, d) => (
            <Textarea id={id} aria-describedby={d} value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
          )}
        </Field>
        {showMessage && (
          <Field
            label={messageRequired ? 'Message to the student' : 'Message to the student (optional)'}
            hint={appStatus === 'additional_information_required' ? 'Say exactly what the student needs to provide. Shown in their portal.' : 'Shown in the student portal. Do not include internal risk details.'}
          >
            {(id, d) => (
              <Textarea id={id} aria-describedby={d} value={studentMessage} maxLength={1000} onChange={(e) => setStudentMessage(e.target.value)} />
            )}
          </Field>
        )}
      </div>
    </Modal>
  );
}
