import { CreditCard, Fingerprint, MonitorSmartphone, ScanFace, ShieldAlert, Users } from 'lucide-react';
import { RiskBadge, RiskScoreRing } from '@/components/ui/Risk';

const signals = [
  { icon: ScanFace, label: 'Face mismatch during payment-destination change', points: 34 },
  { icon: CreditCard, label: 'Refund destination shared by 6 unrelated students', points: 22 },
  { icon: MonitorSmartphone, label: 'Device fingerprint reused across 8 applications', points: 18 },
  { icon: Users, label: 'Online-only enrollment with no recorded attendance', points: 9 },
];

/** Static marketing illustration built from the synthetic "coordinated network" scenario. */
export function HeroPreview() {
  return (
    <div className="relative mx-auto w-full max-w-lg" aria-label="Illustration of an EduShield AI risk assessment" role="img">
      <div className="rounded-2xl border border-white/10 bg-white p-5 shadow-2xl shadow-navy-950/50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-slate-500">Risk assessment · FA-2026-104871</p>
            <p className="mt-1 text-sm font-semibold text-slate-900">Northbridge State University</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <RiskBadge level="critical" />
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">Human review required</span>
            </div>
          </div>
          <RiskScoreRing score={87} level="critical" size={76} />
        </div>
        <div className="mt-5 space-y-2.5">
          {signals.map((s) => (
            <div key={s.label} className="flex items-center gap-3">
              <s.icon className="size-4 shrink-0 text-navy-600" aria-hidden />
              <p className="min-w-0 flex-1 truncate text-xs text-slate-700">{s.label}</p>
              <div className="flex w-24 shrink-0 items-center gap-2">
                <div className="h-1.5 flex-1 rounded-full bg-slate-100">
                  <div className="h-1.5 rounded-full bg-navy-700" style={{ width: `${(s.points / 34) * 100}%` }} />
                </div>
                <span className="tabular w-7 text-right text-xs font-medium text-slate-600">+{s.points}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-5 flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-amber-100">
          <ShieldAlert className="size-4 shrink-0" aria-hidden />
          Recommended: hold refund and open an investigation. No automated denial.
        </div>
      </div>

      <div className="absolute -bottom-14 -left-4 hidden w-60 rounded-xl border border-slate-200 bg-white p-3.5 shadow-raised sm:block lg:-left-10">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-lg bg-red-50 text-risk-critical">
            <Fingerprint className="size-4" aria-hidden />
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-900">Liveness check failed</p>
            <p className="text-[11px] text-slate-500">Screen replay detected · simulated</p>
          </div>
        </div>
      </div>
    </div>
  );
}
