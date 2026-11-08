import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { toast } from 'sonner';
import type { StudentInvitation } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { Field, Input } from '@/components/ui/Field';
import { api, errorMessage } from '@/lib/api';

/** Institution-issued portal access: students cannot register themselves. */
export function InviteStudentDialog({ studentId, open, onOpenChange }: { studentId: string; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StudentInvitation | null>(null);
  const invite = useMutation({
    mutationFn: async () => (await api.post<StudentInvitation>(`/students/${studentId}/invitation`, { email: email.trim() })).data,
    onSuccess: (data) => {
      setResult(data);
      toast.success('Invitation created');
    },
    onError: (err) => setError(errorMessage(err)),
  });

  const close = (next: boolean) => {
    if (!next) {
      setEmail('');
      setError(null);
      setResult(null);
    }
    onOpenChange(next);
  };

  return (
    <Modal
      open={open}
      onOpenChange={close}
      title="Invite student to the portal"
      description="Creates a one-time activation link tied to this student record."
      footer={
        result ? (
          <Button onClick={() => close(false)}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={() => close(false)}>Cancel</Button>
            <Button loading={invite.isPending} disabled={!email.includes('@')} onClick={() => { setError(null); invite.mutate(); }}>Send invitation</Button>
          </>
        )
      }
    >
      {result ? (
        <div className="space-y-3 text-sm text-slate-700">
          <p>Invitation created for {result.email}. It expires {new Date(result.expires_at).toLocaleString()}.</p>
          {result.activation_url && (
            <div className="rounded-lg bg-amber-50 p-3 ring-1 ring-amber-100">
              <p className="font-medium text-amber-900">Development mode: no email was sent.</p>
              <p className="mt-1 text-xs text-amber-900">Give this one-time link to the student. It is never returned in production.</p>
              <code className="mt-2 block text-xs break-all text-slate-800">{result.activation_url}</code>
            </div>
          )}
        </div>
      ) : (
        <Field label="Student's email address" error={error}>
          {(id, d) => <Input id={id} aria-describedby={d} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />}
        </Field>
      )}
    </Modal>
  );
}
