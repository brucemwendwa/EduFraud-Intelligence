import { Play } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { errorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { P } from '@/lib/permissions';
import { useDetectionRun, useInvalidateAfterRun, useStartDetectionRun } from './api';

const FINISHED = ['completed', 'failed'];

/** Starts a background detection run and reports the outcome when it finishes. */
export function RunDetectionButton({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const { can } = useAuth();
  const start = useStartDetectionRun();
  const [runId, setRunId] = useState<string | null>(null);
  const run = useDetectionRun(runId);
  const refresh = useInvalidateAfterRun();
  const reported = useRef<string | null>(null);
  const data = run.data;

  useEffect(() => {
    if (!data || reported.current === data.id || !FINISHED.includes(data.status)) return;
    reported.current = data.id;
    if (data.status === 'completed') {
      toast.success('Detection run completed', {
        description: `${data.applications_scored} applications scored · ${data.alerts_created} new alert(s) · ${data.mode} mode`,
      });
      refresh();
    } else {
      toast.error('Detection run failed', { description: data.error ?? 'See the audit trail for details.' });
    }
  }, [data, refresh]);

  if (!can(P.detectionRun)) return null;
  const busy = start.isPending || (Boolean(runId) && !FINISHED.includes(data?.status ?? ''));
  return (
    <Button
      size={size}
      icon={<Play className="size-4" />}
      loading={busy}
      onClick={() =>
        start.mutate(undefined, {
          onSuccess: (r) => {
            setRunId(r.id);
            toast.info('Detection run started', { description: 'Scoring runs in the background.' });
          },
          onError: (err) => toast.error('Could not start run', { description: errorMessage(err) }),
        })
      }
    >
      {busy ? 'Running detection…' : 'Run detection'}
    </Button>
  );
}
