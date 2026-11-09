import { useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { Field, Textarea } from '@/components/ui/Field';
import { errorMessage } from '@/lib/api';
import { useCreateVerificationRequest } from './api';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accountId: string;
  accountRef: string;
}

/** Opens an identity re-verification request; the pathway follows the student's registered study arrangement. */
export function RequestVerificationDialog({ open, onOpenChange, accountId, accountRef }: Props) {
  const [reason, setReason] = useState('');
  const create = useCreateVerificationRequest();
  const navigate = useNavigate();
  const valid = reason.trim().length >= 5;

  const submit = () =>
    create.mutate(
      { account_id: accountId, reason: reason.trim() },
      {
        onSuccess: (req) => {
          toast.success(`Verification ${req.reference} requested`, { description: `${req.pathway.replace('_', ' ')} pathway · student notified (simulated)` });
          setReason('');
          onOpenChange(false);
          navigate(`/app/verification?tab=requests&selected=${req.id}`);
        },
        onError: (err) => toast.error('Request not created', { description: errorMessage(err) }),
      },
    );

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Request identity verification"
      description={`${accountRef}: on-campus students are asked to visit the verification office; remote and international students choose a remote method.`}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={create.isPending}>Cancel</Button>
          <Button loading={create.isPending} disabled={!valid} onClick={submit}>Send request</Button>
        </>
      }
    >
      <Field label="Reason" hint="Shown on the request timeline and recorded in the audit trail.">
        {(id, describedBy) => (
          <Textarea id={id} aria-describedby={describedBy} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} autoFocus />
        )}
      </Field>
    </Modal>
  );
}
