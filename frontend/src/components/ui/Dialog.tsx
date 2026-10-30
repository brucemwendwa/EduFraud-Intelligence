import * as RDialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Button } from './Button';
import { Field, Textarea } from './Field';

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

const widths = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl' };

export function Modal({ open, onOpenChange, title, description, children, footer, size = 'md' }: ModalProps) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="fixed inset-0 z-50 bg-navy-950/40 backdrop-blur-[2px]" />
        <RDialog.Content
          className={cn(
            'fixed top-1/2 left-1/2 z-50 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2',
            'rounded-xl border border-slate-200 bg-white shadow-raised focus:outline-none',
            widths[size],
          )}
          {...(description ? {} : { 'aria-describedby': undefined })}
        >
          <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
            <div>
              <RDialog.Title className="text-base font-semibold text-slate-900">{title}</RDialog.Title>
              {description && (
                <RDialog.Description className="mt-1 text-sm text-slate-500">{description}</RDialog.Description>
              )}
            </div>
            <RDialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close dialog" className="-mt-1 -mr-2">
                <X className="size-4" />
              </Button>
            </RDialog.Close>
          </div>
          {children && <div className="max-h-[65vh] overflow-y-auto px-5 py-4">{children}</div>}
          {footer && (
            <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3">
              {footer}
            </div>
          )}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}

interface ConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  tone?: 'primary' | 'danger';
  loading?: boolean;
  /** When set, the user must enter a justification which is passed to onConfirm (audited server-side). */
  reasonLabel?: string;
  onConfirm: (reason: string) => void;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  tone = 'primary',
  loading,
  reasonLabel,
  onConfirm,
}: ConfirmProps) {
  const [reason, setReason] = useState('');
  const needsReason = Boolean(reasonLabel);
  const valid = !needsReason || reason.trim().length >= 5;
  return (
    <Modal
      open={open}
      onOpenChange={(o) => {
        if (!o) setReason('');
        onOpenChange(o);
      }}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant={tone === 'danger' ? 'danger' : 'primary'}
            loading={loading}
            disabled={!valid}
            onClick={() => onConfirm(reason.trim())}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {needsReason && (
        <Field label={reasonLabel} hint="Minimum 5 characters. Recorded in the audit log.">
          {(id, describedBy) => (
            <Textarea
              id={id}
              aria-describedby={describedBy}
              value={reason}
              maxLength={500}
              onChange={(e) => setReason(e.target.value)}
              autoFocus
            />
          )}
        </Field>
      )}
    </Modal>
  );
}

interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  side?: 'right' | 'left';
  className?: string;
}

export function Drawer({ open, onOpenChange, title, description, children, footer, side = 'right', className }: DrawerProps) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="fixed inset-0 z-50 bg-navy-950/30" />
        <RDialog.Content
          className={cn(
            'fixed inset-y-0 z-50 flex w-full max-w-lg flex-col bg-white shadow-raised focus:outline-none',
            side === 'right' ? 'right-0 border-l' : 'left-0 border-r',
            'border-slate-200',
            className,
          )}
          {...(description ? {} : { 'aria-describedby': undefined })}
        >
          <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
            <div className="min-w-0">
              <RDialog.Title className="truncate text-base font-semibold text-slate-900">{title}</RDialog.Title>
              {description && (
                <RDialog.Description className="mt-0.5 text-sm text-slate-500">{description}</RDialog.Description>
              )}
            </div>
            <RDialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close panel" className="-mt-1 -mr-2">
                <X className="size-4" />
              </Button>
            </RDialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</div>}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  );
}
