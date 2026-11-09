import { useState } from 'react';
import { toast } from 'sonner';
import type { Role, StaffInvitation } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { Field, Input, Select } from '@/components/ui/Field';
import { errorMessage } from '@/lib/api';
import { useInviteStaff } from './api';

export function InviteStaffDialog({ roles, open, onOpenChange }: { roles: Role[]; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [title, setTitle] = useState('');
  const [roleKey, setRoleKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<StaffInvitation | null>(null);
  const invite = useInviteStaff();
  const valid = email.includes('@') && fullName.trim().length >= 2 && roleKey !== '';

  const close = (next: boolean) => {
    if (!next) {
      setEmail('');
      setFullName('');
      setTitle('');
      setRoleKey('');
      setError(null);
      setResult(null);
    }
    onOpenChange(next);
  };

  const submit = () => {
    setError(null);
    invite.mutate(
      { email: email.trim(), full_name: fullName.trim(), title: title.trim() || null, role_key: roleKey },
      {
        onSuccess: (data) => {
          setResult(data);
          toast.success('Invitation created');
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={close}
      title="Invite a staff member"
      description="They set their own password from a one-time link."
      footer={
        result ? (
          <Button onClick={() => close(false)}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={() => close(false)}>Cancel</Button>
            <Button loading={invite.isPending} disabled={!valid} onClick={submit}>Send invitation</Button>
          </>
        )
      }
    >
      {result ? (
        <div className="space-y-3 text-sm text-slate-700">
          <p>Invitation created for {result.email}, as {result.role_name}.</p>
          {result.activation_url && (
            <div className="rounded-lg bg-amber-50 p-3 ring-1 ring-amber-100">
              <p className="font-medium text-amber-900">No email was sent in this environment.</p>
              <p className="mt-1 text-xs text-amber-900">Share this one-time link securely. It is never returned in production.</p>
              <code className="mt-2 block text-xs break-all text-slate-800">{result.activation_url}</code>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <Field label="Email address">{(id) => <Input id={id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />}</Field>
          <Field label="Full name">{(id) => <Input id={id} value={fullName} maxLength={120} onChange={(e) => setFullName(e.target.value)} />}</Field>
          <Field label="Job title (optional)">{(id) => <Input id={id} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />}</Field>
          <Field label="Role" error={error}>
            {(id, d) => (
              <Select id={id} aria-describedby={d} value={roleKey} onChange={(e) => setRoleKey(e.target.value)}>
                <option value="">Select a role</option>
                {roles.map((role) => <option key={role.key} value={role.key}>{role.name}</option>)}
              </Select>
            )}
          </Field>
        </div>
      )}
    </Modal>
  );
}
