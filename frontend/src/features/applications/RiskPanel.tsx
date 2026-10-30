import { ShieldQuestion } from 'lucide-react';
import type { ApplicationDetail } from '@/api/types';
import { Card } from '@/components/ui/Card';
import { RiskScoreRing, type RiskLevel } from '@/components/ui/Risk';
import { EmptyState } from '@/components/ui/States';
import { dateTime } from '@/lib/format';

/** Current risk assessment summary. Expanded with explainable signals once the detection engine lands. */
export function RiskPanel({ app }: { app: ApplicationDetail }) {
  if (app.risk_score == null) {
    return (
      <Card>
        <EmptyState
          icon={<ShieldQuestion className="size-5" />}
          title="Not yet assessed"
          description="This application has not been scored by the detection engine."
        />
      </Card>
    );
  }
  return (
    <Card className="flex items-center gap-5 p-5">
      <RiskScoreRing score={app.risk_score} level={app.risk_level as RiskLevel} />
      <div>
        <p className="text-sm font-semibold text-slate-900">Current risk assessment</p>
        <p className="text-xs text-slate-500">Assessed {dateTime(app.last_assessed_at)}</p>
      </div>
    </Card>
  );
}
